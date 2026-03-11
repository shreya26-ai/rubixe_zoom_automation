import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key="PASTE_YOUR_KEY_DIRECTLY_HERE")
try:
    # A simple "Hello" test
    response = client.models.generate_content(
        model='gemini-2.0-flash', 
        contents="Hi"
    )
    print("💎 SUCCESS! Your key is working.")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"❌ STILL FAILED: {e}")