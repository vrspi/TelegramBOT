import sys
from types import SimpleNamespace
import types
from pathlib import Path
import json
import asyncio
import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Stub heavy dependencies before importing project modules
sys.modules.setdefault('MetaTrader5', types.SimpleNamespace())
sys.modules.setdefault('together', types.SimpleNamespace(Together=lambda api_key: None))

from bot.agents.trading_agent import TradingAgent

DATA_FILE = Path(__file__).resolve().parents[1] / "data.txt"
LINES = DATA_FILE.read_text(encoding="utf-8").splitlines()

def extract(start, end):
    """Extract lines from data.txt ignoring empty and quoted ones."""
    out = []
    for i in range(start - 1, end):
        line = LINES[i].strip()
        if not line or line.startswith('>'):
            continue
        out.append(line)
    return "\n".join(out)

OPEN_MESSAGE = extract(14, 22)
BREAKEVEN_MESSAGE = extract(158, 158)
CLOSE_HALF_MESSAGE = extract(212, 212)

class DummyClient:
    def __init__(self, response=None):
        self.response = response

    def chat_completion(self, *_, **__):
        return self.response

def test_break_even_pattern():
    agent = TradingAgent(together_client=DummyClient(), mt5_service=None)
    decision = asyncio.run(agent.analyze_and_decide(BREAKEVEN_MESSAGE))
    assert decision["action"] == "set_breakeven"

def test_close_half_pattern():
    agent = TradingAgent(together_client=DummyClient(), mt5_service=None)
    decision = asyncio.run(agent.analyze_and_decide(CLOSE_HALF_MESSAGE))
    assert decision["action"] == "close_half"

def test_llm_function_call_open_trade():
    args = {
        "direction": "buy",
        "entry": 2498.0,
        "stop_loss": 2494.0,
        "take_profit": [2503.0],
    }
    tool_call = SimpleNamespace(function=SimpleNamespace(name="open_trade", arguments=json.dumps(args)))
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[tool_call]))])
    agent = TradingAgent(together_client=DummyClient(response), mt5_service=None)
    decision = asyncio.run(agent.analyze_and_decide(OPEN_MESSAGE))
    assert decision["action"] == "buy"
    assert decision["entry_price"] == args["entry"]
    assert decision["take_profit"] == args["take_profit"]
