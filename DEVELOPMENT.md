# TelegramBOT Development Guide

This document provides guidelines and information for developers working on the TelegramBOT project.

## Project Architecture

### Core Components

1. **Telegram Integration**: Handles connection to Telegram API and listens for messages
   - `bot/telegram_client_handler.py`: Manages Telegram client connection and message handling

2. **Trading Logic**: Contains the intelligence for trading decisions
   - `bot/agents/trading_agent.py`: Core trading logic and decision making
   - Implements direct pattern matching for trading signals and management commands

3. **MetaTrader 5 Integration**: Handles all MT5 operations
   - `services/mt5_service.py`: Provides functions for interacting with MT5 platform
   - Manages positions, orders, account info, and market data

4. **AI Integration**: (optional) Uses Together AI for advanced analysis
   - `services/together_client.py`: Client for Together AI API
   - Used for complex message analysis when direct pattern matching is insufficient

5. **GUI**: Simple interface for monitoring bot status
   - `gui/main_app.py`: PySide6-based GUI application

### Data Flow

1. Telegram message → `telegram_client_handler.py` → `trading_agent.py` → Decision
2. If decision requires action → `mt5_service.py` → MT5 Platform
3. Result of action → `telegram_client_handler.py` → GUI update

## Development Workflow

### Setting Up Development Environment

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd TelegramBOT
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv_py310
   # Windows
   venv_py310\Scripts\activate
   # Linux/Mac
   source venv_py310/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file with your credentials:
   ```
   TELEGRAM_API_ID=your_api_id
   TELEGRAM_API_HASH=your_api_hash
   TELEGRAM_PHONE_NUMBER=your_phone_number
   TELEGRAM_SOURCE_CHANNEL_ID=channel_id
   TOGETHER_API_KEY=your_together_api_key
   MT5_LOGIN=your_mt5_account_number
   MT5_PASSWORD=your_mt5_password
   MT5_SERVER=your_mt5_server
   ```

### Testing Changes

1. For MT5 service tests:
   ```bash
   python core/test.py
   ```

2. For MetaTrader configuration verification:
   ```bash
   python utils/mt5_config_helper.py
   ```

3. Running the bot in debug mode:
   ```bash
   python core/main.py --debug
   ```

## Implementing New Features

### Adding New Command Recognition

To add a new command recognition to the `analyze_and_decide` method in `trading_agent.py`:

1. Identify the pattern for the new command
2. Add a new pattern matching condition in the method
3. Return an appropriate action dictionary

Example:
```python
# Detect new command pattern
if "trailing stop" in lower_msg:
    logging.warning("Using direct pattern matching for trailing stop command")
    return {
        "action": "set_trailing_stop",
        "symbol": "XAUUSD",
        "reasoning": "Direct pattern matching detected trailing stop command",
        "risk_assessment": "Setting trailing stop to protect profits"
    }
```

### Implementing New Actions

To implement a new action in the `execute_decision` method:

1. Add a new condition for the action type
2. Implement the logic to handle the action
3. Return appropriate success/failure response

Example:
```python
# Handle trailing stop action
if action.lower() == "set_trailing_stop":
    if not self.mt5_service:
        logging.error("MT5 service not available for trailing stop operation")
        return {"success": False, "message": "MT5 service not available"}
    
    # Implement trailing stop logic here
    # ...
    
    return {
        "success": True,
        "message": "Set trailing stop for positions"
    }
```

### Adding MT5 Functionality

To add new functionality to the MT5 service:

1. Add a new method to the `MT5Service` class in `services/mt5_service.py`
2. Implement the logic using the MT5 API
3. Add proper error handling and logging

## Code Style Guide

- Follow PEP 8 for Python code style
- Use type hints for function parameters and return values
- Add docstrings to all classes and methods
- Use logging instead of print statements
- Handle exceptions properly with try/except blocks

## Pull Request Process

1. Create a new branch for your feature
2. Implement the feature with tests
3. Submit a pull request with a detailed description
4. Address any review comments
5. Once approved, merge into the main branch

## Troubleshooting Common Issues

### MT5 Connection Problems

- Verify MT5 is running and AutoTrading is enabled
- Check that the credentials in `.env` are correct
- Make sure MT5 terminal has internet access

### Telegram API Issues

- Verify API ID and hash are correct
- Make sure the phone number is correctly formatted
- Check if you need to reauthorize the session

### Order Execution Problems

- Check if account has sufficient margin
- Ensure proper symbol names are used
- Verify stop levels are within broker requirements 