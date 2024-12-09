import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import json5
from services.together_client import TogetherClient

class TradingDecision(Enum):
    EXECUTE_TRADE = "execute_trade"
    MODIFY_TRADE = "modify_trade"
    CLOSE_TRADE = "close_trade"
    SET_BREAKEVEN = "set_breakeven"
    NO_ACTION = "no_action"
    NEED_CLARIFICATION = "need_clarification"

@dataclass
class AccountInfo:
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: float

@dataclass
class MarketContext:
    symbol: str
    bid: float
    ask: float
    spread: float
    volume: float
    time: str

class TradingAgent:
    def __init__(self, together_client: TogetherClient, max_history: int = 10):
        self.together_client = together_client
        self.message_history: List[Dict] = []
        self.max_history = max_history
        
    def add_to_history(self, message: str, decision: Dict):
        """Add message and its analysis to history."""
        self.message_history.append({
            "message": message,
            "decision": decision,
            "timestamp": self.get_current_timestamp()
        })
        
        # Keep only recent history
        if len(self.message_history) > self.max_history:
            self.message_history.pop(0)

    def get_current_timestamp(self) -> str:
        """Get current timestamp in a readable format."""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def format_trade_history(self, trades: Dict) -> str:
        """Format current trades into a readable string."""
        if not trades:
            return "No active trades."
        
        trade_strings = []
        for symbol, trade in trades.items():
            trade_strings.append(
                f"{symbol}: {trade.direction.upper()} at {trade.entry}, "
                f"SL={trade.stop_loss}, TP={trade.take_profit}, "
                f"State={trade.state.name}"
            )
        return "\n".join(trade_strings)

    def format_message_history(self) -> str:
        """Format recent message history into a readable string."""
        if not self.message_history:
            return "No message history."
        
        history_strings = []
        for entry in self.message_history[-5:]:  # Last 5 messages
            history_strings.append(
                f"[{entry['timestamp']}] {entry['message']}\n"
                f"Decision: {entry['decision'].get('decision', 'Unknown')}"
            )
        return "\n\n".join(history_strings)

    def generate_analysis_prompt(self, message: str, account_info: AccountInfo, 
                               market_context: MarketContext, trades: Dict) -> str:
        """Generate a comprehensive prompt for the LLM."""
        prompt_template = '''You are an expert trading assistant specializing in XAUUSD (Gold) trading signals.
Your role is to analyze trading messages and make informed decisions. IMPORTANT: When a clear trading signal is given (like "Gold buy/sell now"), you should EXECUTE the trade immediately at market price, even if stop loss and take profit levels are not specified.

Current Market Context:
- Symbol: {symbol}
- Current Bid: {bid}
- Current Ask: {ask}
- Spread: {spread}
- Time: {time}

Account Status:
- Balance: ${balance:,.2f}
- Equity: ${equity:,.2f}
- Free Margin: ${free_margin:,.2f}
- Margin Level: {margin_level}%

Active Trades:
{trades}

Recent Message History:
{history}

New Message to Analyze:
"{message}"

Analyze this message carefully and provide:
1. A detailed analysis of the message intent
2. Risk assessment considering current market and account conditions
3. A clear trading decision

IMPORTANT RULES:
1. For "buy/sell now" messages, ALWAYS execute the trade immediately at market price
2. If stop loss and take profit are not specified, execute the trade anyway
3. Default risk management will be applied by the system
4. Do not ask for clarification on direct trading signals

Return your response in this JSON format:
{{
    "analysis": "Your step-by-step reasoning about the message",
    "risk_assessment": "Your evaluation of the risk",
    "decision": "EXECUTE_TRADE/MODIFY_TRADE/CLOSE_TRADE/SET_BREAKEVEN/NO_ACTION/NEED_CLARIFICATION",
    "action_params": {{
        "symbol": "XAUUSD.sml",
        "direction": "buy/sell",
        "entry": float or null,
        "stop_loss": float or null,
        "take_profit": [float] or null,
        "reason": "Brief explanation of the decision"
    }}
}}'''

        return prompt_template.format(
            symbol=market_context.symbol,
            bid=market_context.bid,
            ask=market_context.ask,
            spread=market_context.spread,
            time=market_context.time,
            balance=account_info.balance,
            equity=account_info.equity,
            free_margin=account_info.free_margin,
            margin_level=account_info.margin_level,
            trades=self.format_trade_history(trades),
            history=self.format_message_history(),
            message=message
        )

    async def analyze_and_decide(self, message: str, account_info: AccountInfo, 
                               market_context: MarketContext, trades: Dict) -> Dict:
        """Analyze message and make a trading decision."""
        try:
            # Generate and send prompt to LLM
            prompt = self.generate_analysis_prompt(message, account_info, market_context, trades)
            response = self.together_client.chat_completion(prompt)
            
            if not response:
                logging.error("Failed to get LLM response")
                return self.create_error_decision("Failed to get LLM response")

            # Extract content from response
            try:
                content = response.choices[0].message.content
                if not content:
                    logging.error("Empty response content from LLM")
                    return self.create_error_decision("Empty response content from LLM")
            except (IndexError, AttributeError) as e:
                logging.error(f"Error extracting content from response: {e}")
                return self.create_error_decision("Error extracting content from response")

            # Extract JSON from the response
            try:
                # First, try to find JSON between triple backticks
                if '```' in content:
                    parts = content.split('```')
                    for part in parts:
                        # Remove 'json' language identifier if present
                        if part.startswith('json\n'):
                            part = part[5:]
                        # Try to parse this part
                        try:
                            parsed_response = json5.loads(part.strip())
                            if isinstance(parsed_response, dict) and 'analysis' in parsed_response:
                                break
                        except:
                            continue
                else:
                    # If no backticks, try to parse the whole content
                    parsed_response = json5.loads(content)
            except Exception as e:
                logging.error(f"Failed to parse LLM response: {e}")
                logging.debug(f"Raw content: {content}")
                return self.create_error_decision("Failed to parse LLM response")

            # Validate the parsed response
            if not isinstance(parsed_response, dict) or 'analysis' not in parsed_response:
                logging.error("Invalid response format from LLM")
                return self.create_error_decision("Invalid response format from LLM")

            # Log the analysis for debugging
            logging.info(f"LLM Analysis: {parsed_response.get('analysis')}")
            logging.info(f"Risk Assessment: {parsed_response.get('risk_assessment')}")

            # Create decision object
            try:
                decision_str = parsed_response.get('decision', 'NO_ACTION')
                decision = {
                    "decision": TradingDecision[decision_str.upper()],
                    "params": parsed_response.get('action_params', {}),
                    "reasoning": parsed_response.get('analysis', ''),
                    "risk_assessment": parsed_response.get('risk_assessment', '')
                }
            except KeyError:
                logging.error(f"Invalid decision value: {decision_str}")
                return self.create_error_decision(f"Invalid decision value: {decision_str}")

            # Add to history
            self.add_to_history(message, decision)

            return decision

        except Exception as e:
            logging.error(f"Error in analyze_and_decide: {e}", exc_info=True)
            return self.create_error_decision(str(e))

    def create_error_decision(self, error_message: str) -> Dict:
        """Create an error decision object."""
        return {
            "decision": TradingDecision.NO_ACTION,
            "params": {},
            "reasoning": f"Error: {error_message}",
            "risk_assessment": "Unable to assess risk due to error"
        } 