import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

# Explicitly pull and check the key before starting
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("❌ Critical Error: GEMINI_API_KEY not found in .env file.")
else:
    # Use the explicit key to avoid environment confusion
    client = genai.Client(api_key=api_key)
    print("✅ Gemini Client Initialized.")

def extract_updates_with_llm(transcript_text):
    print("🧠 Sending transcript to Gemini (v3 SDK) for extraction...")
    try:
        # Use the flash model which is most stable for JSON extraction
        response = client.models.generate_content(
            model='gemini-2.0-flash', 
            contents=f"Extract student updates from this transcript: {transcript_text}"
        )
        return response.text
    except Exception as e:
        # This will now print the exact server response if it fails
        print(f"❌ Gemini Error: {e}")
        return None
    
import os
import json
from google import genai
from dotenv import load_dotenv
from database import SessionLocal
from models import StudentUpdate

load_dotenv()

# ==================================================
# 🔴 MODERN GEMINI CONFIGURATION (google-genai)
# ==================================================
# The new SDK automatically looks for 'GEMINI_API_KEY' in your .env
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def extract_updates_with_llm(transcript_text):
    print("🧠 Sending transcript to Gemini (v3 SDK) for extraction...")
    
    prompt = f"""
    You are a data processing assistant. Extract student names, batch IDs, 
    and project updates from this Zoom transcript.
    
    RETURN ONLY A VALID JSON OBJECT:
    {{
      "updates": [
        {{"student_name": "Name", "batch_id": "ID", "update_text": "Update description"}}
      ]
    }}

    Transcript:
    {transcript_text}
    """

    try:
        # The new 'models.generate_content' syntax
        response = client.models.generate_content(
            model='gemini-2.0-flash', # Or gemini-1.5-flash
            contents=prompt
        )
        
        # Clean the response text
        text_data = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(text_data)
    except Exception as e:
        print(f"❌ Gemini API Error: {e}")
        return {"updates": []}

def save_updates_to_db(updates_list):
    db = SessionLocal()
    try:
        for item in updates_list:
            new_update = StudentUpdate(
                student_name=item.get('student_name'),
                batch_id=item.get('batch_id'),
                update_text=item.get('update_text')
            )
            db.add(new_update)
        db.commit()
        print(f"✅ Successfully saved {len(updates_list)} updates to PostgreSQL.")
    except Exception as e:
        print(f"❌ Database Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    if os.path.exists("test_transcript.txt"):
        with open("test_transcript.txt", "r", encoding="utf-8") as f:
            sample_text = f.read()
        
        result = extract_updates_with_llm(sample_text)
        updates = result.get("updates", [])
        if updates:
            save_updates_to_db(updates)
    else:
        print("❌ Please create 'test_transcript.txt' first.")