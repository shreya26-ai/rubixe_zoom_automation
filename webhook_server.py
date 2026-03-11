from fastapi import FastAPI, Request
import uvicorn
import hashlib, hmac, base64, asyncio
import os
import time
from dotenv import load_dotenv

from database import SessionLocal, engine
from models import Base, Participant
from queue_manager import add_participant, remove_participant, get_queue

from pymongo import MongoClient
from recording_downloader import download_recordings
from transcriber import transcribe_audio
from transcript_parser import parse_vtt
from llm_extractor import extract_batch_and_work

# 🧠 AI QUEUE + VOICE
from ai_queue_processor import (
    process_queue_safely,
    meeting_ready_event,
    speaker_done_event,
    current_speaker
)
from ai_voice import speak

load_dotenv()

# ==================================================
# 🔴 GLOBAL STATE
# ==================================================
ACTIVE_MEETING_ID = None
meeting_start_time = None

# ==================================================
# APP INIT
# ==================================================
app = FastAPI()
Base.metadata.create_all(bind=engine)

# ==================================================
# ENV
# ==================================================
ZOOM_WEBHOOK_SECRET = os.getenv("ZOOM_WEBHOOK_SECRET")

# ==================================================
# MONGO
# ==================================================
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client["zoom_reports"]
weekly_reports_col = mongo_db["weekly_reports"]

# ==================================================
# 🔊 AI VOICE ANNOUNCER
# ==================================================
async def announce_participant(name: str):
    print(f"🔊 Speaking → {name}")
    speak(f"{name}, please speak now")

# ==================================================
# 🚀 START QUEUE PROCESSOR (RUNS ONCE)
# ==================================================
@app.on_event("startup")
async def start_ai_queue():
    print("🧠 AI Queue Processor Started")
    asyncio.create_task(process_queue_safely(announce_participant))

# ==================================================
# ZOOM WEBHOOK
# ==================================================
@app.post("/zoom/webhook")
async def zoom_webhook(request: Request):
    global ACTIVE_MEETING_ID, meeting_start_time

    body = await request.json()

    # ✅ FIX: DEFINE VARIABLES IMMEDIATELY
    event = body.get("event")
    payload = body.get("payload", {})
    meeting_obj = payload.get("object", {})
    participant_obj = meeting_obj.get("participant", {})

    # ------------------------------------------------
    # 🔐 URL VALIDATION (Handshake)
    # ------------------------------------------------
    if event == "endpoint.url_validation":
        plain_token = payload.get("plainToken")
        
        # Ensure 'ZOOM_WEBHOOK_SECRET' in .env is your 'Secret Token'
        secret_token = os.getenv("ZOOM_WEBHOOK_SECRET")
        
        # Create HMAC-SHA256 Hash as Hex
        hash_for_zoom = hmac.new(
            secret_token.encode('utf-8'),
            plain_token.encode('utf-8'),
            hashlib.sha256
        ).hexdigest() 

        print(f"✅ Validation Challenge Received. Sending Hex Token.")
        
        return {
            "plainToken": plain_token,
            "encryptedToken": hash_for_zoom
        }

    # ------------------------------------------------
    # ✅ DATABASE CONTEXT START
    # ------------------------------------------------
    db = SessionLocal()
    try:
        # ✅ PARTICIPANT JOINED
        if event == "meeting.participant_joined":
            name = participant_obj.get("user_name")
            meeting_id = meeting_obj.get("id")

            if ACTIVE_MEETING_ID is None:
                ACTIVE_MEETING_ID = meeting_id
                meeting_start_time = time.time()
                print(f"🧠 ACTIVE_MEETING_ID → {ACTIVE_MEETING_ID}")
                print("⏳ Waiting 5 minutes for participants to join...")

                # 🕒 WARM-UP TIMER
                async def warmup_timer():
                    await asyncio.sleep(300)  # 5 minutes
                    meeting_ready_event.set()
                    print("🚀 Warm-up complete. AI may start calling speakers.")

                asyncio.create_task(warmup_timer())

            add_participant(name)

            db.add(
                Participant(
                    meeting_id=meeting_id,
                    name=name,
                    queue_position=len(get_queue())
                )
            )
            db.commit() # Commit to finalize the row

            print(f"📩 {name} joined | Queue: {list(get_queue())}")

        # ❌ PARTICIPANT LEFT
        elif event == "meeting.participant_left":
            name = participant_obj.get("user_name")
            remove_participant(name)
            print(f"❌ {name} left meeting")

            # 🎯 IF CURRENT SPEAKER LEFT → ALLOW NEXT
            if name == current_speaker:
                print(f"🟢 Speaker completed: {name}")
                speaker_done_event.set()

        # 🧾 TRANSCRIPT READY
        elif event == "recording.transcript_completed":
            print("🧾 Transcript generation completed by Zoom")

        # 🎥 RECORDING COMPLETED
        elif event == "recording.completed":
            meeting_id = meeting_obj.get("id")
            recording_files = meeting_obj.get("recording_files", [])

            files = download_recordings(meeting_id, recording_files)
            print("📂 Files downloaded:", files)

            for file_path in files:
                if file_path.endswith(".vtt"):
                    print(f"📝 Parsing transcript {file_path}")
                    transcript = parse_vtt(file_path)
                elif file_path.endswith((".mp3", ".m4a")):
                    print(f"🎧 Transcribing audio {file_path}")
                    transcript = transcribe_audio(file_path)
                else:
                    continue

                print("🧠 Transcript:", transcript)
                extracted = extract_batch_and_work(transcript)

                weekly_reports_col.insert_one({
                    "meeting_id": meeting_id,
                    "batch_id": extracted.get("batch_id", "UNKNOWN"),
                    "weekly_work": extracted.get("weekly_work", transcript),
                    "raw_transcript": transcript,
                    "confidence": extracted.get("confidence", 0.9)
                })

                print("✅ Weekly report stored")

    except Exception as e:
        print(f"❌ Error processing webhook: {e}")
    finally:
        db.close() # ✅ Always close the session

    return {"status": "ok"}

# ==================================================
# RUN SERVER
# ==================================================
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)