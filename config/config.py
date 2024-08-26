import json
import os
from dotenv import load_dotenv

def load_config():
    # Load .env file
    load_dotenv()

    # Load JSON config
    with open('config.json', 'r') as f:
        json_config = json.load(f)

    # Merge configurations, prioritizing .env values
    config = {
        'TELEGRAM_API_ID': os.getenv('TELEGRAM_API_ID'),
        'TELEGRAM_API_HASH': os.getenv('TELEGRAM_API_HASH'),
        'TELEGRAM_PHONE_NUMBER': os.getenv('TELEGRAM_PHONE_NUMBER'),
        'TELEGRAM_SOURCE_CHANNEL_ID': os.getenv('TELEGRAM_SOURCE_CHANNEL_ID'),
        'TELEGRAM_DESTINATION_CHAT_ID': os.getenv('TELEGRAM_DESTINATION_CHAT_ID'),
        'TOGETHER_API_KEY': os.getenv('TOGETHER_API_KEY'),
        'MT5_LOGIN': os.getenv('MT5_LOGIN'),
        'MT5_PASSWORD': os.getenv('MT5_PASSWORD'),
        'MT5_SERVER': os.getenv('MT5_SERVER'),
    }

    # Update with JSON config (will not overwrite existing values)
    for key, value in json_config.items():
        if key not in config or config[key] is None:
            config[key] = value

    missing_keys = [key for key, value in config.items() if value is None]
    if missing_keys:
        raise ValueError(f"Missing configuration values for: {', '.join(missing_keys)}")

    return config