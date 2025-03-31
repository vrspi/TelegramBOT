# Telegram MT5 Trading Bot

A sophisticated trading bot that automatically processes trading signals from Telegram channels and executes them in MetaTrader 5, using AI-powered signal analysis.

## Features

- **Telegram Signal Monitoring**: Automatically reads and processes trading signals from designated Telegram channels.
- **AI-Powered Analysis**: Uses Together AI's powerful LLM models to interpret trading signals and make execution decisions.
- **MetaTrader 5 Integration**: Directly connects to MT5 to execute trades with proper risk management.
- **Real-time Logging**: Comprehensive logging of all operations for auditing and debugging.
- **User Interface**: Simple GUI to monitor bot status and operations.
- **Automatic Recovery**: Resilient design that handles connection issues and API failures.

## Prerequisites

- Python 3.8 or higher
- MetaTrader 5 installed
- Telegram account with API access
- Together AI API key
- MT5 trading account (demo or live)

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/telegram-mt5-trading-bot.git
cd telegram-mt5-trading-bot
```

2. Create and activate a virtual environment:
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python -m venv venv
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure your environment variables in the `.env` file:
```
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHANNEL_ID=your_channel_id

# Telegram Client Configuration
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_SOURCE_CHANNEL_ID=source_channel_id
TELEGRAM_DESTINATION_CHAT_ID=destination_chat_id
TELEGRAM_PHONE_NUMBER=your_phone_number

# Together AI API Key
TOGETHER_API_KEY=your_together_api_key

# MT5 Configuration
MT5_LOGIN=your_mt5_account_number
MT5_PASSWORD=your_mt5_password
MT5_SERVER=your_mt5_server
```

## Configuring MetaTrader 5

Before running the bot, make sure your MetaTrader 5 is properly configured:

1. Make sure MT5 is running and logged in to your account
2. Enable AutoTrading:
   - Go to Tools > Options > Expert Advisors
   - Enable "Allow automated trading"
   - Enable "Allow DLL imports"
   - Ensure the AutoTrading button in the toolbar is enabled (green)

3. Verify Symbol Availability:
   - Run our MT5 configuration helper to find the correct symbol name for your broker:
   ```bash
   python utils/mt5_config_helper.py
   ```
   - This will detect available symbols and identify which one works best for your broker
   
## Running the Bot

1. Run the MT5 connection test to ensure everything is set up correctly:
```bash
python core/test.py
```

2. Start the main trading bot:
```bash
python core/main.py
```

The bot will launch with a GUI interface where you can monitor its status and logs.

## Troubleshooting Common Issues

### MT5 Connection Issues

If you're having trouble connecting to MT5:

1. Verify your credentials in the `.env` file
2. Make sure MT5 is running
3. Check that AutoTrading is enabled in MT5
4. Run `python utils/mt5_config_helper.py` to diagnose the issue

### IC Markets Special Configuration

For IC Markets users:

- The correct symbol for gold trading might be `XAUUSD.a` instead of `XAUUSD`
- Use the IOC filling mode (the bot will automatically detect this)
- Check your margin requirements - IC Markets has specific margin requirements for gold trading

### Telegram Authentication Issues

If you're having trouble with Telegram authentication:

1. Verify your API ID and hash in the `.env` file
2. Make sure the phone number is correctly formatted (include country code)
3. You may need to approve the login attempt on your Telegram account

## Project Structure

```
├── bot/                   # Telegram bot and message processing
│   ├── agents/            # AI trading agents
│   └── telegram_client_handler.py
├── config/                # Configuration handling
├── core/                  # Core application files
│   ├── main.py            # Main entry point
│   └── test.py            # Testing utilities
├── gui/                   # GUI components
├── services/              # Services for MT5, Together API, etc.
├── utils/                 # Utility scripts
│   └── mt5_config_helper.py
├── .env                   # Environment variables
├── requirements.txt       # Python dependencies
└── README.md              # This file
```

## Security Considerations

- Your `.env` file contains sensitive credentials. Never share it or commit it to public repositories.
- Consider using a dedicated MT5 account with limited funds for bot trading.
- Test thoroughly with a demo account before using real funds.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements

- [MetaTrader 5 Python API](https://www.mql5.com/en/docs/python_metatrader5)
- [Telethon](https://docs.telethon.dev/en/stable/) for Telegram client functionality
- [Together AI](https://together.ai/) for LLM capabilities
- [PySide6](https://wiki.qt.io/Qt_for_Python) for the GUI interface