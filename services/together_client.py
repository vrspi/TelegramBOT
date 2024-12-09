import logging
import os
from together import Together
from typing import Optional, Any

class TogetherClient:
    def __init__(self, api_key: str):
        """Initialize the Together AI client."""
        os.environ['TOGETHER_API_KEY'] = api_key
        self.client = Together(api_key=api_key)
        self.model = "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo"
        
    def chat_completion(self, prompt: str) -> Optional[Any]:
        """Send a chat completion request to Together AI."""
        try:
            # Log prompt without Unicode characters
            safe_prompt = prompt.encode('ascii', errors='replace').decode()
            logging.info(f"Sending prompt to Together API: {safe_prompt}")
            
            # Make the API call using the chat completions endpoint
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert trading assistant specializing in XAUUSD (Gold) trading signals."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Lower temperature for more focused responses
                max_tokens=1024
            )
            
            # Log the response safely
            if response:
                safe_response = str(response).encode('ascii', errors='replace').decode()
                logging.info(f"Received response from Together API: {safe_response}")
            
            return response
            
        except Exception as e:
            logging.error(f"Error in Together API call: {str(e)}", exc_info=True)
            return None
