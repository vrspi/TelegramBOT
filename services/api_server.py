from fastapi import FastAPI
from threading import Thread
import uvicorn
import logging

class APIServer:
    def __init__(self, mt5_service=None):
        self.mt5_service = mt5_service
        self.app = FastAPI()
        self.thread = None
        self.setup_routes()

    def setup_routes(self):
        @self.app.get('/account')
        async def account():
            if not self.mt5_service:
                return {}
            return self.mt5_service.get_account_info()

        @self.app.get('/logs')
        async def logs():
            try:
                with open('trading_bot.log', 'r', encoding='utf-8') as f:
                    return f.read().splitlines()
            except FileNotFoundError:
                logging.warning('Log file not found')
                return []

    def start(self):
        def _run():
            uvicorn.run(self.app, host='0.0.0.0', port=8000, log_level='info')
        self.thread = Thread(target=_run, daemon=True)
        self.thread.start()

    def stop(self):
        if self.thread and self.thread.is_alive():
            # uvicorn server stops when process exits; nothing special needed
            pass
