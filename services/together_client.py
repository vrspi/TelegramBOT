from together import Together
import logging

class TogetherClient:
    def __init__(self, api_key):
        self.client = Together(api_key=api_key)

    def chat_completion(self, prompt):
        try:
            logging.info(f"Sending prompt to Together API: {prompt}")
            response = self.client.chat.completions.create(
                model="meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
                messages=[{"role": "system", "content": prompt}],
                max_tokens=512,
                temperature=0.7,
                top_p=0.7,
                top_k=50,
                repetition_penalty=1,
                stop=["<|eot_id|>","<|eom_id|>"]
            # This causes the response to be streamed as a generator
            )

            logging.info(f"Received response from Together API: {response}")
            
            if not response or not response.choices or not response.choices[0].message.content:
                logging.warning("Received an empty or invalid response from Together API.")
                return None

            return response
        except Exception as e:
            logging.error(f"Failed to get completion from Together API: {e}")
            return None
