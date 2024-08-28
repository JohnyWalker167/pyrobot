import os
from dotenv import load_dotenv

load_dotenv('config.env', override=True)

API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')



