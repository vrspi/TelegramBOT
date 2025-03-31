# TelegramBOT Updates and Changelog

## Latest Updates (March 31, 2025)

### New Features

#### Direct Pattern Matching for Trade Management Commands
- **Breakeven Command**: Added recognition for "set break even" and "breakeven" commands
  - Automatically moves stop loss to entry price for all open positions
  - Protects profits and eliminates risk once price has moved in your favor

- **Close Half Position**: Added recognition for "close half", "secure half", and "secure profits" commands
  - Automatically closes 50% of each open position
  - Allows securing partial profits while maintaining exposure to the market
  - For very small positions (below 0.02 lots), will close the entire position

#### Improved Position Management
- Enhanced the MT5 service to support partial position closing
- Added proper volume calculation and rounding to standard lot sizes
- Improved handling of multiple take profit levels

### Bug Fixes
- Fixed error handling in position modification and closing operations
- Added better logging for trade execution confirmations
- Ensured stop loss and take profit levels are properly validated and reported

### Technical Improvements
- Added comprehensive .gitignore file for better version control
  - Includes Python, virtual environment, and IDE-specific exclusions
  - Added frontend-related exclusions (Node.js, React, Angular, Vue, etc.)
  - Prevents sensitive data and credentials from being committed
- Implemented more robust error handling throughout the codebase
- Improved code documentation for key trading methods

## Upcoming Features
- Close at specific take profit level command
- Move stop loss to specific level command
- Trailing stop functionality
- Trade history analysis and reporting
- Automated trade journaling

## Usage Instructions

### Managing Trades with Commands
Send these commands in the Telegram channel to manage your open positions:

- `set break even` - Move stop loss to entry price for all positions
- `close half` - Close 50% of all open positions to secure partial profits

Trading signals are also recognized automatically:
- `Gold buy now` or `XAUUSD buy now` - Execute a buy trade
- `Gold sell now` or `XAUUSD sell now` - Execute a sell trade

Stop loss and take profit can be specified in the message:
```
Gold buy now 1900-1905
SL: 1895
TP: 1910
TP: 1915
TP: 1920
``` 