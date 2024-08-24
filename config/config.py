import os
from dotenv import load_dotenv

def load_config():
    load_dotenv()

    config = {
        'TELEGRAM_BOT_TOKEN': os.getenv('TELEGRAM_BOT_TOKEN'),
        'TELEGRAM_CHANNEL_ID': os.getenv('TELEGRAM_CHANNEL_ID'),
        'TOGETHER_API_KEY': os.getenv('TOGETHER_API_KEY'),
        'TELEGRAM_API_ID': os.getenv('TELEGRAM_API_ID'),
        'TELEGRAM_API_HASH': os.getenv('TELEGRAM_API_HASH'),
        'TELEGRAM_SOURCE_CHANNEL_ID': os.getenv('TELEGRAM_SOURCE_CHANNEL_ID'),
        'TELEGRAM_DESTINATION_CHAT_ID': os.getenv('TELEGRAM_DESTINATION_CHAT_ID'),
        'MT5_LOGIN': os.getenv('MT5_LOGIN'),
        'MT5_PASSWORD': os.getenv('MT5_PASSWORD'),
        'MT5_SERVER': os.getenv('MT5_SERVER'),
    }

    missing_keys = [key for key, value in config.items() if value is None]
    if missing_keys:
        raise ValueError(f"Missing configuration values for: {', '.join(missing_keys)}")

    return config
