import os
import json
import asyncio
from groq import Groq
from dotenv import load_dotenv
from sqlalchemy.orm import Session
# Import your DB setup from your existing files
from database import SessionLocal, engine
from models import MeetingUpdate, Base

load_dotenv()

# Initialize Groq
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Ensure the table exists
Base.metadata.create_all(bind=engine)

async def process_with_groq(file_path):
    if not os.path.exists(file_path):
        print(f"❌ Error: {file_path} not found.")
        return

    print(f"📂 Reading {file_path}...")
    with open(file_path, "r", encoding="utf-8") as f:
        transcript_content = f.read()

    # We use a strict system prompt to ensure clean JSON
    prompt = f"""
    Extract meeting updates into a JSON array of objects. 
    Each object MUST have: "name", "batch_id", "project_id", "update".
    Transcript: {transcript_content}
    """

    try:
        print("🚀 Sending to Groq (Llama 3.3)...")
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Return ONLY a JSON object containing a list named 'updates'."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"} 
        )

        # 1. Parse Groq's response
        raw_data = json.loads(completion.choices[0].message.content)
        updates = raw_data.get("updates", [])

        if not updates:
            print("⚠️ No updates found in the transcript.")
            return

        # 2. Save to PostgreSQL
        print(f"💾 Saving {len(updates)} entries to PostgreSQL...")
        db = SessionLocal()
        try:
            for item in updates:
                new_update = MeetingUpdate(
                    name=item.get("name"),
                    batch_id=str(item.get("batch_id")),
                    project_id=str(item.get("project_id")),
                    update=item.get("update")
                )
                db.add(new_update)
            db.commit()
            print("✨ Success! Database updated.")
        except Exception as db_err:
            print(f"❌ Database Error: {db_err}")
            db.rollback()
        finally:
            db.close()

    except Exception as e:
        print(f"❌ Groq API Error: {e}")

if __name__ == "__main__":
    asyncio.run(process_with_groq("test_transcript.txt"))