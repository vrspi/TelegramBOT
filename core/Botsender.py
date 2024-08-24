import asyncio
from telegram import Bot

# Your bot token from BotFather
bot_token = '7251976812:AAEwQFzhrgdiE4BAbcc3qIlGeHTgcrJ0Lwk'
# The chat ID of the channel (e.g., @mychannel or a numeric ID)
channel_id = -1002170038761

# Define an async function to send the message
async def send_message():
    bot = Bot(token=bot_token)
    await bot.send_message(chat_id=channel_id, text="buy gold now!")
    print("Message sent!")

# Run the async function
asyncio.run(send_message())
