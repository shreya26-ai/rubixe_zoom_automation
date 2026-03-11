import requests
import os
import time
from dotenv import load_dotenv

load_dotenv()

def clean_vtt(vtt_text):
    """Simple function to remove timestamps and VTT headers"""
    lines = vtt_text.splitlines()
    clean_lines = []
    for line in lines:
        # Skip VTT headers and timestamp lines
        if "WEBVTT" in line or "-->" in line or not line.strip():
            continue
        clean_lines.append(line.strip())
    return "\n".join(clean_lines)

def process_transcript_task(url, token):
    # Add the token to the URL as a query parameter for Zoom
    authenticated_url = f"{url}?access_token={token}"
    
    try:
        print(f"📥 Downloading transcript from Zoom...")
        response = requests.get(authenticated_url)
        
        if response.status_code == 200:
            raw_text = response.text
            # 1. Clean the transcript
            clean_text = clean_vtt(raw_text)
            
            # 2. Save a local copy for debugging
            filename = f"meeting_transcript_{int(time.time())}.txt"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(clean_text)
            
            print(f"✅ Cleaned transcript saved to {filename}")
            
            # 3. NEXT: We will add the Ollama LLM call here
            return clean_text
        else:
            print(f"❌ Failed to download: {response.status_code}")
    except Exception as e:
        print(f"❌ Error in processing: {e}")