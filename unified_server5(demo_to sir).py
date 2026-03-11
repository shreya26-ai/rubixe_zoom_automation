import hashlib, hmac, asyncio, os, time, datetime, re, requests, json
import uvicorn, pyttsx3, numpy as np, sounddevice as sd
import torch
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from sqlalchemy import text
from dotenv import load_dotenv
from groq import Groq

# Local Imports
from database import SessionLocal, engine, Base
from models import Participant, MeetingUpdate

load_dotenv()

# ==================================================
# 🔴 GLOBAL STATE & CONFIG
# ==================================================
ACTIVE_MEETING_ID = None
SEEN_PARTICIPANTS = set() 
IS_MEETING_READY = asyncio.Event() 
HOST_NAME = "Ashok" # Matches your host exclusion requirement
V_CABLE_ID = 1           

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ==================================================
# 🧹 DATABASE CLEANUP (AUTO-ERASE)
# ==================================================
def clear_db():
    """Wipes the database tables on startup to ensure a fresh session."""
    print("🧹 Cleaning database for new session...")
    db = SessionLocal()
    try:
        db.execute(text("TRUNCATE TABLE participants, meeting_updates RESTART IDENTITY;"))
        db.commit()
        print("✅ Database cleared successfully.")
    except Exception as e:
        print(f"⚠️ Could not clear DB: {e}")
    finally:
        db.close()

Base.metadata.create_all(bind=engine)
model, _ = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad', force_reload=False, onnx=True)

# ==================================================
# 🔊 VOICE ENGINE
# ==================================================
def speak(text):
    print(f"🤖 Bot: {text}")
    try:
        engine_instance = pyttsx3.init()
        engine_instance.setProperty('rate', 140)
        engine_instance.say(text)
        engine_instance.runAndWait()
        engine_instance.stop()
        time.sleep(0.5)
    except Exception as e: print(f"🔊 Voice Error: {e}")

# ==================================================
# 🎙️ AUDIO MONITORING (VAD) WITH RUNNING DIALOGUE
# ==================================================
async def monitor_speech_local(participant_name):
    print(f"🎙️ Monitoring {participant_name}... (12s start / 7s silence)")
    HARDWARE_RATE, MODEL_RATE = 48000, 16000
    DOWNSAMPLE = HARDWARE_RATE // MODEL_RATE
    talking, last_sound, start_time = False, time.time(), time.time()
    max_peak = 0.0

    def callback(indata, frames, time_info, status):
        nonlocal talking, last_sound, max_peak
        audio_float32 = np.frombuffer(indata, dtype=np.int16)[::DOWNSAMPLE].astype(np.float32) / 32768.0
        with torch.no_grad():
            confidence = model(torch.from_numpy(audio_float32), MODEL_RATE).item()
            if confidence > max_peak: max_peak = confidence
            if confidence > 0.15: 
                if not talking:
                    # NEW: Prints dialogue status to terminal in real-time
                    print(f"💬 [LIVE DIALOGUE] {participant_name} started speaking...")
                talking = True; last_sound = time.time()

    try:
        with sd.RawInputStream(device=V_CABLE_ID, samplerate=HARDWARE_RATE, blocksize=1536, channels=1, dtype='int16', callback=callback):
            while True:
                now = time.time()
                if not talking and (now - start_time) > 12.0:
                    print(f"   🔇 Timeout: No speech. (Peak: {max_peak:.4f})")
                    return False 
                if talking and (now - last_sound) > 7.0:
                    print(f"   ✅ {participant_name} finished update. (Peak: {max_peak:.4f})")
                    return True      
                await asyncio.sleep(0.1)
    except Exception as e: return False

# ==================================================
# ✨ TRANSCRIPT EXTRACTION (SMART MAPPING)
# ==================================================
async def process_transcript_task(url, token):
    print("⚡ Extracting updates with official participant mapping...")
    db = SessionLocal()
    try:
        # Map phonetic errors to official names
        official_names = [p.name for p in db.query(Participant).filter(Participant.meeting_id == str(ACTIVE_MEETING_ID)).all()]
        name_list_str = ", ".join(official_names)

        response = requests.get(f"{url}?access_token={token}")
        if response.status_code == 200:
            raw_vtt = response.text
            # Remove timestamps and Bot dialogue
            clean_text = re.sub(r'(\d{2}:\d{2}:\d{2}\.\d{3} --> .*?\n)|(WEBVTT\n)|(^\d+\n)', '', raw_vtt, flags=re.MULTILINE)
            clean_text = re.sub(r'^(Ashok|Bot|🤖 Bot):.*$', '', clean_text, flags=re.MULTILINE)
            if len(clean_text) > 8000: clean_text = clean_text[-8000:] 
            
            prompt = f"Official Names: {name_list_str}. Extract JSON: {{\"updates\": [{{\"name\": \"Official Name\", \"batch_id\": \"ID\", \"update\": \"Desc\"}}]}} Transcript: {clean_text}"
            completion = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "system", "content": "Return ONLY JSON."}, {"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            updates = json.loads(completion.choices[0].message.content).get("updates", [])
            print("\n--- 📝 FINAL MEETING DIALOGUE SUMMARY ---")
            for item in updates:
                print(f"👤 {item.get('name')}: {item.get('update')}")
                db.add(MeetingUpdate(name=item.get("name"), batch_id=str(item.get("batch_id")), update=item.get("update")))
            db.commit()
            print("------------------------------------------\n💾 Database Updated.")
    except Exception as e: print(f"❌ Error: {e}")
    finally: db.close()

# ==================================================
# 🚀 THE MODERATOR LOOP (WITH STABLE COUNTING)
# ==================================================
async def unified_moderator_loop():
    print("⏳ Waiting for Zoom Webhook to start meeting...")
    await IS_MEETING_READY.wait()
    
    # Live status snapshots during wait
    for i in range(4):
        db = SessionLocal()
        pending_count = db.query(Participant).filter(Participant.status == 'pending', Participant.meeting_id == str(ACTIVE_MEETING_ID)).count()
        db.close()
        print(f"⏳ Settle period ({60 - (i*15)}s remaining) | Queue: {pending_count}")
        await asyncio.sleep(15)

    print("🚀 Moderator Loop Active!")
    speak("Hello everyone. This is strictly an update call. Updates must be given verbally.")
    
    empty_queue_counter = 0

    while True:
        db = SessionLocal()
        try:
            # 1. Fetch next person
            learner = db.query(Participant).filter(Participant.status == 'pending', Participant.meeting_id == str(ACTIVE_MEETING_ID)).order_by(Participant.joined_at.asc()).first()
            if not learner:
                learner = db.query(Participant).filter(Participant.status == 'retry', Participant.meeting_id == str(ACTIVE_MEETING_ID)).order_by(Participant.joined_at.asc()).first()

            if learner:
                empty_queue_counter = 0 # Reset counter if we found someone
                status = learner.status
                learner.status = 'processing'; db.commit()
                
                msg = f"Next up is {learner.name}." if status == 'pending' else f"Second call for {learner.name}."
                speak(f"{msg} Please state your update.")
                
                if await monitor_speech_local(learner.name):
                    learner.status = 'spoken'; speak(f"Thank you {learner.name}.")
                else:
                    learner.status = 'retry' if status == 'pending' else 'absent'
                    speak("Moving to end of queue." if learner.status == 'retry' else "Moving on.")
                db.commit()
            else:
                # 2. 🏁 IMPROVED END LOGIC
                empty_queue_counter += 5
                if empty_queue_counter >= 30: # After 30s of actual silence
                    speak("Everyone has been called. Meeting complete. You may end the call.")
                    print("✅ Meeting finished. Waiting for Zoom to process transcript...")
                    # We don't 'break' here so the server stays alive for the transcript webhook
                    empty_queue_counter = -99999 # Prevent repeating the message
                elif empty_queue_counter > 0:
                    print(f"🏁 Queue appears empty. Final check in {30 - empty_queue_counter}s...")

            await asyncio.sleep(5)
        except Exception as e: 
            print(f"❌ Loop Error: {e}")
            db.rollback()
        finally: 
            db.close()

# ==================================================
# ⚡ FASTAPI WEBHOOK (WITH SESSION LOCK)
# ==================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    clear_db()
    asyncio.create_task(unified_moderator_loop())
    yield

app = FastAPI(lifespan=lifespan)

@app.post("/zoom/webhook")
async def zoom_webhook(request: Request):
    global ACTIVE_MEETING_ID, SEEN_PARTICIPANTS
    body = await request.json()
    event = body.get("event")

    if event == "meeting.participant_joined":
        p_obj = body.get("payload", {}).get("object", {})
        p_id, name = p_obj.get("id"), p_obj.get("participant", {}).get("user_name")

        if name and name.lower() == HOST_NAME.lower(): return {"status": "ok"}

        # STABLE SESSION LOCK: Don't reset if it's the same meeting
        if ACTIVE_MEETING_ID is None:
            print(f"🌟 Meeting Started: {p_id}.")
            ACTIVE_MEETING_ID = p_id
            IS_MEETING_READY.set()
        elif ACTIVE_MEETING_ID != p_id:
            print(f"🔄 Meeting Switched: {p_id}. Resetting memory.")
            ACTIVE_MEETING_ID = p_id
            SEEN_PARTICIPANTS.clear()

        if name and name not in SEEN_PARTICIPANTS:
            db = SessionLocal()
            exists = db.query(Participant).filter(Participant.name == name, Participant.meeting_id == str(ACTIVE_MEETING_ID)).first()
            if not exists:
                print(f"➕ [JOIN] {name} added to queue.")
                db.add(Participant(name=name, meeting_id=str(ACTIVE_MEETING_ID), status='pending'))
                db.commit()
                SEEN_PARTICIPANTS.add(name)
            db.close()
        else:
            print(f"♻️ [REJOIN] {name} already in queue. Skipping.")

    if event == "recording.transcript_completed":
        payload = body.get("payload", {}).get("object", {})
        file = next((f for f in payload.get("recording_files", []) if f.get("file_type") == "TRANSCRIPT"), None)
        if file: asyncio.create_task(process_transcript_task(file.get("download_url"), body.get("download_token")))

    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)