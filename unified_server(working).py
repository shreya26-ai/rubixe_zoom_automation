import hashlib, hmac, asyncio, os, time, datetime, re
import requests, json
import uvicorn, pyttsx3, numpy as np, sounddevice as sd
import torch
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
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
IS_MEETING_READY = asyncio.Event() 
HOST_NAME = "Your Name"  # 👈 Update to your exact Zoom Display Name
V_CABLE_ID = 1           # 👈 Double-check this ID with sd.query_devices()

# Initialize Groq Client
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Create tables in DB
Base.metadata.create_all(bind=engine)

# ✅ Load Silero VAD
model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad', force_reload=False, onnx=True)

# ==================================================
# 🔊 ROBUST VOICE ENGINE
# ==================================================
def speak(text):
    """Refreshes the engine for every sentence to prevent audio hangs."""
    print(f"🤖 Bot: {text}")
    try:
        engine_instance = pyttsx3.init()
        engine_instance.setProperty('rate', 135)
        engine_instance.say(text)
        engine_instance.runAndWait()
        engine_instance.stop()
        # Small delay to ensure Windows releases the audio driver
        time.sleep(0.5)
    except Exception as e:
        print(f"🔊 Voice Error: {e}")

# ==================================================
# 🎙️ AUDIO MONITORING (VAD)
# ==================================================
async def monitor_speech_local(participant_name):
    # 12 seconds to start speaking, 7 seconds of silence to consider them "done"
    print(f"🎙️ Monitoring {participant_name}... (12s start timeout / 7s silence limit)")
    HARDWARE_RATE, MODEL_RATE = 48000, 16000
    DOWNSAMPLE = HARDWARE_RATE // MODEL_RATE
    talking, last_sound, start_time = False, time.time(), time.time()
    max_detected_level = 0.0

    def callback(indata, frames, time_info, status):
        nonlocal talking, last_sound, max_detected_level
        audio_int16 = np.frombuffer(indata, dtype=np.int16)
        audio_float32 = audio_int16[::DOWNSAMPLE].astype(np.float32) / 32768.0
        with torch.no_grad():
            confidence = model(torch.from_numpy(audio_float32), MODEL_RATE).item()
            if confidence > max_detected_level:
                max_detected_level = confidence
            
            # Lowered threshold to 0.15 for better sensitivity
            if confidence > 0.15: 
                talking = True
                last_sound = time.time()

    try:
        with sd.RawInputStream(device=V_CABLE_ID, samplerate=HARDWARE_RATE, blocksize=1536, channels=1, dtype='int16', callback=callback):
            while True:
                now = time.time()
                
                # 1. Wait 12 seconds for them to START talking
                if not talking and (now - start_time) > 12.0:
                    print(f"   🔇 Timeout: No speech started. (Peak: {max_detected_level:.4f})")
                    return False
                
                # 2. If they ARE talking, wait for 7 seconds of silence to consider them finished
                if talking and (now - last_sound) > 7.0:
                    print(f"   ✅ Update Captured. (Peak: {max_detected_level:.4f})")
                    return True
                
                await asyncio.sleep(0.1)
    except Exception as e:
        print(f"❌ Audio Input Error: {e}")
        return False
    
# ==================================================
# ✨ TRANSCRIPT CLEANING & AI
# ==================================================
def clean_vtt(vtt_text):
    clean_text = re.sub(r'WEBVTT\n?', '', vtt_text)
    clean_text = re.sub(r'^\d+\n', '', clean_text, flags=re.MULTILINE)
    clean_text = re.sub(r'\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}\n', '', clean_text)
    return "\n".join([line.strip() for line in clean_text.split('\n') if line.strip()])

async def send_to_ai_groq(cleaned_text):
    try:
        print("⚡ Sending to Groq Cloud...")
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Return ONLY a JSON object with a list called 'updates'."},
                {"role": "user", "content": f"Extract updates: {cleaned_text}"}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(completion.choices[0].message.content).get("updates", [])
    except Exception as e:
        print(f"❌ Groq Error: {e}"); return []

async def process_transcript_task(url, token):
    try:
        response = requests.get(f"{url}?access_token={token}")
        if response.status_code == 200:
            structured_list = await send_to_ai_groq(clean_vtt(response.text))
            db = SessionLocal()
            for item in structured_list:
                db.add(MeetingUpdate(
                    name=item.get("name"), batch_id=str(item.get("batch_id")),
                    project_id=str(item.get("project_id")), update=item.get("update")
                ))
            db.commit(); db.close()
            print("💾 Database Updated from Transcript.")
    except Exception as e: print(f"❌ Transcript Error: {e}")

# ==================================================
# 🚀 MAIN MODERATOR LOOP
# ==================================================
async def unified_moderator_loop():
    await IS_MEETING_READY.wait()
    print("🚀 Moderator Loop Active!")
    while True:
        db = SessionLocal()
        try:
            learner = db.query(Participant).filter(Participant.status == 'pending').order_by(Participant.joined_at.asc()).first()
            if learner:
                learner.status = 'processing'
                db.commit()
                db.refresh(learner)

                speak(f"Next up is {learner.name}. Please state your update.")
                await asyncio.sleep(0.5) # Breath gap
                
                if await monitor_speech_local(learner.name):
                    learner.status = 'spoken'
                    db.commit()
                    speak(f"Thank you {learner.name}.")
                else:
                    learner.status = 'absent'
                    db.commit()
                    speak(f"Moving on.")
            await asyncio.sleep(3)
        except Exception as e: 
            print(f"❌ Loop Error: {e}"); db.rollback()
        finally: db.close()

# ==================================================
# ⚡ FASTAPI APP
# ==================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(unified_moderator_loop())
    yield

app = FastAPI(lifespan=lifespan)

@app.post("/zoom/webhook")
async def zoom_webhook(request: Request):
    global ACTIVE_MEETING_ID
    body = await request.json()
    event = body.get("event")

    if event == "endpoint.url_validation":
        token = body.get("payload", {}).get("plainToken")
        secret = os.getenv("ZOOM_WEBHOOK_SECRET").encode('utf-8')
        hash_val = hmac.new(secret, token.encode('utf-8'), hashlib.sha256).hexdigest()
        return {"plainToken": token, "encryptedToken": hash_val}

    if event == "recording.transcript_completed":
        payload = body.get("payload", {}).get("object", {})
        token = body.get("download_token") 
        file = next((f for f in payload.get("recording_files", []) if f.get("file_type") == "TRANSCRIPT"), None)
        if file: asyncio.create_task(process_transcript_task(file.get("download_url"), token))

    if event == "meeting.participant_joined":
        db = SessionLocal()
        name = body.get("payload", {}).get("object", {}).get("participant", {}).get("user_name")
        if name and name.lower() != HOST_NAME.lower():
            print(f"📝 Joined: {name}")
            if not ACTIVE_MEETING_ID:
                ACTIVE_MEETING_ID = body.get("payload", {}).get("object", {}).get("id")
                asyncio.get_event_loop().call_later(2, IS_MEETING_READY.set)
            db.add(Participant(name=name, meeting_id=ACTIVE_MEETING_ID, status='pending'))
            db.commit()
        db.close()
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)