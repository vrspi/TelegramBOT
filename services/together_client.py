import logging
import os
import time
from together import Together
from typing import Optional, Any

class TogetherClient:
    def __init__(self, api_key: str):
        """Initialize the Together AI client."""
        os.environ['TOGETHER_API_KEY'] = api_key
        self.client = Together(api_key=api_key)
        self.model = "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo"
        self.fallback_model = "meta-llama/Llama-3.1-70B-Instruct"
        self.max_retries = 3
        self.retry_delay = 2  # seconds
        
    def chat_completion(self, prompt: str) -> Optional[Any]:
        """Send a chat completion request to Together AI with retry logic."""
        # Log prompt without sensitive Unicode characters
        safe_prompt = prompt.encode('ascii', errors='replace').decode()
        logging.info(f"Sending prompt to Together API: {safe_prompt[:200]}...")
        
        # First try with primary model
        response = self._attempt_completion(prompt, self.model)
        
        # If primary model fails, try fallback model
        if not response:
            logging.warning(f"Primary model {self.model} failed, trying fallback model {self.fallback_model}")
            response = self._attempt_completion(prompt, self.fallback_model)
            
        return response
    
    def _attempt_completion(self, prompt: str, model: str) -> Optional[Any]:
        """Make API call with retries."""
        for attempt in range(self.max_retries):
            try:
                # Make the API call using the chat completions endpoint
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are an expert trading assistant specializing in XAUUSD (Gold) trading signals."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,  # Lower temperature for more focused responses
                    max_tokens=1024
                )
                
                # Log a truncated version of the response
                if response and hasattr(response, 'choices') and response.choices:
                    content = response.choices[0].message.content
                    safe_content = str(content)[:200].encode('ascii', errors='replace').decode()
                    logging.info(f"Received response from Together API: {safe_content}...")
                
                return response
                
            except Exception as e:
                logging.error(f"Error in Together API call (attempt {attempt+1}/{self.max_retries}): {str(e)}")
                if attempt < self.max_retries - 1:
                    # Exponential backoff
                    wait_time = self.retry_delay * (2 ** attempt)
                    logging.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                    
        return None
