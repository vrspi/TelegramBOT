import os
import sys
import logging
import json
import MetaTrader5 as mt5
from datetime import datetime

# Add the project root directory to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Import project configuration 
from config.config import load_config
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("mt5_config.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

class MT5ConfigHelper:
    """Helper class to analyze and fix MT5 configuration issues."""
    
    def __init__(self):
        # Load environment variables and configuration
        load_dotenv()
        self.config = load_config()
        self.initialized = False
        
    def initialize_mt5(self, login=None, password=None, server=None):
        """Initialize MT5 with credentials."""
        try:
            # If credentials are not provided, try from config
            login = login or self.config.get('MT5_LOGIN')
            password = password or self.config.get('MT5_PASSWORD')
            server = server or self.config.get('MT5_SERVER')
            
            # Check if we have all required credentials
            if not all([login, password, server]):
                logging.error("Missing MT5 credentials. Please provide login, password, and server.")
                return False
                
            # Initialize MT5
            if not mt5.initialize(login=int(login), password=password, server=server):
                logging.error("Failed to initialize MT5")
                return False
                
            self.initialized = True
            logging.info(f"MT5 initialized successfully with account {login} on server {server}")
            return True
        except Exception as e:
            logging.error(f"Error initializing MT5: {e}", exc_info=True)
            return False
            
    def shutdown(self):
        """Shutdown MT5 connection."""
        if self.initialized:
            mt5.shutdown()
            self.initialized = False
            logging.info("MT5 connection closed")
            
    def analyze_account(self):
        """Analyze the current MT5 account."""
        if not self._ensure_initialized():
            return
            
        # Get account info
        account_info = mt5.account_info()
        if not account_info:
            logging.error("Failed to get account info")
            return
            
        # Print account details
        logging.info("=== ACCOUNT INFORMATION ===")
        logging.info(f"Login: {account_info.login}")
        logging.info(f"Server: {account_info.server}")
        logging.info(f"Company: {account_info.company}")
        logging.info(f"Balance: {account_info.balance} {account_info.currency}")
        logging.info(f"Equity: {account_info.equity} {account_info.currency}")
        logging.info(f"Margin: {account_info.margin} {account_info.currency}")
        logging.info(f"Free Margin: {account_info.margin_free} {account_info.currency}")
        logging.info(f"Margin Level: {account_info.margin_level}%")
        logging.info(f"Leverage: 1:{account_info.leverage}")
        logging.info(f"Trade Allowed: {account_info.trade_allowed}")
        
        # Analyze account type and permissions
        self._analyze_account_permissions(account_info)
            
    def _analyze_account_permissions(self, account_info):
        """Analyze account trading permissions."""
        # Check if trading is allowed for this account
        if not account_info.trade_allowed:
            logging.warning("Trading is not allowed for this account")
            logging.warning("Possible causes:")
            logging.warning("- You may be using an investor password (read-only)")
            logging.warning("- The account may be suspended or closed")
            logging.warning("- The account may have restrictions")
            logging.warning("Action: Use the master password or contact your broker")
        
        # Check terminal permissions
        terminal_info = mt5.terminal_info()
        if not terminal_info.trade_allowed:
            logging.warning("AutoTrading is disabled in MT5 terminal")
            logging.warning("Action: Enable AutoTrading in MT5:")
            logging.warning("1. Tools > Options > Expert Advisors > Allow automated trading")
            logging.warning("2. Enable the 'AutoTrading' button in the toolbar (should be green)")
        
        # Check if we have sufficient margin
        if account_info.margin_level is not None and account_info.margin_level < 100:
            logging.warning(f"Low margin level: {account_info.margin_level}%")
            logging.warning("Trading may be restricted due to low margin level")
            logging.warning("Action: Deposit more funds or close some positions")
    
    def analyze_symbol(self, symbol="XAUUSD"):
        """Analyze a specific trading symbol."""
        if not self._ensure_initialized():
            return
        
        # Try to select the symbol first
        if not mt5.symbol_select(symbol, True):
            logging.warning(f"Could not select {symbol} in Market Watch")
            logging.warning("Possible causes:")
            logging.warning("- The symbol name might be incorrect for your broker")
            logging.warning("- The symbol might not be available in your account")
            logging.warning(f"Action: Try variations like {symbol}.a, {symbol}.m, etc.")
            self._find_similar_symbols(symbol)
            return
            
        # Get symbol info
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            logging.error(f"Failed to get symbol info for {symbol}")
            return
            
        # Print symbol details
        logging.info(f"=== SYMBOL INFORMATION: {symbol} ===")
        logging.info(f"Bid: {symbol_info.bid}, Ask: {symbol_info.ask}")
        logging.info(f"Spread: {symbol_info.spread} points")
        logging.info(f"Digits: {symbol_info.digits}")
        logging.info(f"Contract Size: {symbol_info.trade_contract_size}")
        logging.info(f"Min Volume: {symbol_info.volume_min}")
        logging.info(f"Max Volume: {symbol_info.volume_max}")
        logging.info(f"Volume Step: {symbol_info.volume_step}")
        logging.info(f"Trade Mode: {symbol_info.trade_mode}")
        
        # Analyze filling modes
        self._analyze_filling_modes(symbol_info)
        
        # Analyze stop levels
        self._analyze_stop_levels(symbol_info)
        
    def _analyze_filling_modes(self, symbol_info):
        """Analyze symbol filling modes."""
        filling_mode = symbol_info.filling_mode
        logging.info("=== FILLING MODES ===")
        
        modes = []
        if filling_mode & mt5.ORDER_FILLING_FOK:
            modes.append("FOK (Fill or Kill)")
        if filling_mode & mt5.ORDER_FILLING_IOC:
            modes.append("IOC (Immediate or Cancel)")
        if filling_mode & mt5.ORDER_FILLING_RETURN:
            modes.append("RETURN (Return remainder)")
            
        if not modes:
            logging.warning("No filling modes detected. Default to IOC for most brokers.")
        else:
            logging.info(f"Supported filling modes: {', '.join(modes)}")
            if mt5.ORDER_FILLING_IOC in filling_mode:
                logging.info("Recommended to use IOC filling mode for IC Markets")
                
    def _analyze_stop_levels(self, symbol_info):
        """Analyze symbol stop levels."""
        logging.info("=== STOP LEVELS ===")
        logging.info(f"Minimum Stop Level: {symbol_info.trade_stops_level} points")
        
        if symbol_info.trade_stops_level > 0:
            logging.info(f"Stop loss and take profit must be at least {symbol_info.trade_stops_level} points away from current price")
        else:
            logging.info("No minimum distance for stop loss and take profit")
    
    def test_order_functionality(self, symbol="XAUUSD", volume=None):
        """Test order check and margin calculation for a symbol."""
        if not self._ensure_initialized():
            return
            
        # Try to select the symbol
        if not mt5.symbol_select(symbol, True):
            logging.error(f"Could not select {symbol} in Market Watch")
            return
            
        # Get symbol info
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            logging.error(f"Failed to get symbol info for {symbol}")
            return
            
        # Use minimum volume if not specified
        if volume is None:
            volume = symbol_info.volume_min
            
        # Get current price
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            logging.error(f"Failed to get tick for {symbol}")
            return
            
        logging.info(f"=== TESTING ORDER FUNCTIONALITY: {symbol} ===")
        logging.info(f"Volume: {volume} lots")
        logging.info(f"Current price: Bid={tick.bid}, Ask={tick.ask}")
        
        # Test margin calculation
        self._test_margin_calculation(symbol, volume, tick)
        
        # Test order check
        self._test_order_check(symbol, volume, tick)
    
    def _test_margin_calculation(self, symbol, volume, tick):
        """Test margin calculation for a specific symbol and volume."""
        logging.info("=== MARGIN CALCULATION ===")
        
        # Calculate margin for buy
        buy_margin = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, symbol, volume, tick.ask)
        if buy_margin is not None:
            account_info = mt5.account_info()
            free_margin = account_info.margin_free if account_info else 0
            
            logging.info(f"Buy margin required: {buy_margin}")
            logging.info(f"Free margin available: {free_margin}")
            
            if free_margin < buy_margin:
                logging.warning("Insufficient margin for this trade")
                logging.warning(f"Need {buy_margin}, have {free_margin}")
                logging.warning(f"Shortfall: {buy_margin - free_margin}")
                
                # Calculate maximum affordable volume
                if buy_margin > 0:
                    max_volume = (free_margin * 0.9) * volume / buy_margin
                    max_volume = round(max_volume / symbol_info.volume_step) * symbol_info.volume_step
                    max_volume = min(max_volume, symbol_info.volume_max)
                    max_volume = max(max_volume, symbol_info.volume_min)
                    
                    logging.info(f"Maximum affordable volume: approximately {max_volume} lots")
            else:
                logging.info("Margin check passed")
        else:
            logging.error("Failed to calculate margin")
    
    def _test_order_check(self, symbol, volume, tick):
        """Test order check functionality with various filling modes."""
        logging.info("=== ORDER CHECK ===")
        
        # Create base request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY,
            "price": tick.ask,
            "deviation": 50,
            "magic": 12345,
            "comment": "configuration test",
            "type_time": mt5.ORDER_TIME_GTC,
        }
        
        # First try without filling mode
        logging.info("Testing order check without filling type")
        result = mt5.order_check(request)
        self._log_check_result(result)
        
        # Try different filling modes
        for filling_type, name in [
            (mt5.ORDER_FILLING_FOK, "FOK"),
            (mt5.ORDER_FILLING_IOC, "IOC"),
            (mt5.ORDER_FILLING_RETURN, "RETURN")
        ]:
            request_copy = request.copy()
            request_copy["type_filling"] = filling_type
            logging.info(f"Testing with filling mode: {name}")
            result = mt5.order_check(request_copy)
            self._log_check_result(result)
            
            if result is None:
                logging.error(f"Order check returned None with {name} filling mode")
                error_code = mt5.last_error()
                logging.error(f"MT5 error code: {error_code}")
                if error_code == 10030:  # Invalid filling mode
                    logging.warning(f"The broker doesn't support {name} filling mode")
            elif result.retcode == 0:
                logging.info(f"✓ {name} filling mode is supported and working")
    
    def _log_check_result(self, result):
        """Log order check result details."""
        if result is None:
            error_code = mt5.last_error()
            logging.error(f"Order check returned None, error code: {error_code}")
            return
            
        if result.retcode == 0:
            logging.info(f"Order check successful: {result.comment}")
            logging.info(f"Margin required: {result.margin}")
        else:
            logging.warning(f"Order check failed: {result.comment}, code: {result.retcode}")
            
    def find_gold_symbol(self):
        """Attempt to find the correct gold symbol for this broker."""
        if not self._ensure_initialized():
            return
            
        logging.info("=== SEARCHING FOR GOLD SYMBOL ===")
        
        # Try different possible symbol names for gold
        symbols_to_try = ["XAUUSD", "XAUUSD.a", "XAUUSD.m", "GOLD", "GOLD.a", "GOLD.m"]
        
        for symbol in symbols_to_try:
            if mt5.symbol_select(symbol, True):
                symbol_info = mt5.symbol_info(symbol)
                if symbol_info:
                    logging.info(f"✓ {symbol} found and selected")
                    
                    # Get current price
                    tick = mt5.symbol_info_tick(symbol)
                    if tick:
                        logging.info(f"Current price: Bid={tick.bid}, Ask={tick.ask}")
                        
                        # Test a simple order check
                        request = {
                            "action": mt5.TRADE_ACTION_DEAL,
                            "symbol": symbol,
                            "volume": symbol_info.volume_min,
                            "type": mt5.ORDER_TYPE_BUY,
                            "price": tick.ask,
                            "deviation": 50,
                            "magic": 12345,
                            "comment": "test",
                            "type_time": mt5.ORDER_TIME_GTC,
                            "type_filling": mt5.ORDER_FILLING_IOC
                        }
                        
                        result = mt5.order_check(request)
                        if result and result.retcode == 0:
                            logging.info(f"✓✓ {symbol} is fully functional for trading")
                            logging.info(f"Recommended to use {symbol} for gold trading")
                            return symbol
                        else:
                            if result:
                                logging.warning(f"Order check failed for {symbol}: {result.comment}, code: {result.retcode}")
                            else:
                                logging.warning(f"Order check returned None for {symbol}")
            else:
                logging.info(f"× {symbol} not found")
                
        logging.warning("Could not find a fully functional gold symbol")
        return None
    
    def _find_similar_symbols(self, base_symbol):
        """Find symbols similar to the base symbol."""
        logging.info(f"Searching for symbols similar to {base_symbol}...")
        
        # Get all available symbols
        symbols = mt5.symbols_get()
        if not symbols:
            logging.error("Failed to get symbols list")
            return
            
        # Search for symbols containing the base name
        base_name = base_symbol.split('.')[0]  # Remove any suffix
        matches = []
        
        for sym in symbols:
            if base_name.lower() in sym.name.lower():
                matches.append(sym.name)
                
        if matches:
            logging.info(f"Found similar symbols: {', '.join(matches)}")
        else:
            logging.info(f"No symbols found containing '{base_name}'")
    
    def _ensure_initialized(self):
        """Ensure MT5 is initialized."""
        if not self.initialized:
            logging.error("MT5 is not initialized. Please call initialize_mt5() first.")
            return False
        return True

def main():
    """Main function for CLI tool."""
    helper = MT5ConfigHelper()
    
    # Initialize MT5
    if not helper.initialize_mt5():
        logging.error("Failed to initialize MT5. Please check credentials.")
        return
        
    try:
        # Analyze account
        helper.analyze_account()
        
        # Find gold symbol
        gold_symbol = helper.find_gold_symbol()
        
        # If found, analyze it
        if gold_symbol:
            helper.analyze_symbol(gold_symbol)
            
            # Test order functionality
            helper.test_order_functionality(gold_symbol)
            
        logging.info("Configuration analysis complete")
        
    finally:
        helper.shutdown()

if __name__ == "__main__":
    main() 