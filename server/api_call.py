import requests
import time
import random
from openai import OpenAI
from openai import RateLimitError, APIError, APITimeoutError
import os

def generate_response(query, api_key=None, model=None, max_retries=3, base_delay=1,
                       temperature=0, seed=13):
    if api_key is None:
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
    if model is None:
        model = "gpt-4o-mini"

    client = OpenAI(api_key=api_key)

    for attempt in range(max_retries):
        try:
            # Add small random delay to avoid rate limiting
            if attempt > 0:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"Retrying in {delay:.2f} seconds... (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)

            # temperature=0 + a fixed seed: same input should produce the same
            # output across repeated runs on the same document (best-effort --
            # OpenAI doesn't guarantee bit-for-bit determinism even so, but this
            # removes the main source of run-to-run drift in claim counts).
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": query}
                ],
                temperature=temperature,
                seed=seed,
            )
            
            print(f'{"Type: " + str(type(completion.choices[0].message))}')
            print(completion.choices[0].message)
            return completion.choices[0].message
            
        except RateLimitError as e:
            print(f"Rate limit hit on attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                print("Max retries reached for rate limit. Returning None.")
                return None
            # Exponential backoff for rate limits
            delay = base_delay * (2 ** attempt) * 2 + random.uniform(0, 2)
            print(f"Waiting {delay:.2f} seconds before retry...")
            time.sleep(delay)
            
        except (APIError, APITimeoutError) as e:
            print(f"API error on attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                print("Max retries reached for API error. Returning None.")
                return None
                
        except Exception as e:
            print(f"Unexpected error on attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                print("Max retries reached for unexpected error. Returning None.")
                return None
    
    return None

    # response = requests.post(url, headers=headers, json=data)
    # if response.status_code != 200:
    #     print("Status Code:", response.status_code)
    #     print("Response Text:", response.text)

    # response.raise_for_status()
    # return response.text