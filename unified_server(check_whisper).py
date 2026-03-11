import hashlib, hmac, asyncio, os, time, datetime, re, requests, json
import uvicorn, pyttsx3, numpy as np, sounddevice as sd
import torch, smtplib
from email.message import EmailMessage
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from groq import Groq
from faster_whisper import WhisperModel

# Local Imports
from database import SessionLocal, engine, Base
from models import Participant, MeetingUpdate

load_dotenv()

# ==================================================
# 🔴 GLOBAL STATE & CONFIG
# ==================================================
ACTIVE_MEETING_ID = None
IS_MEETING_READY = asyncio.Event() 
HOST_NAME = "Your Name"  
V_CABLE_ID = 1           
REPORT_EMAIL = "manager@example.com"
SENDER_EMAIL = os.getenv("EMAIL_USER")
SENDER_PASS = os.getenv("EMAIL_PASS")
LAST_ACTIVITY_TIME = time.time()

# AI Models
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
vad_model, _ = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad', force_reload=False, onnx=True)
# Using 'tiny.en' for speed; change to 'base.en' for more accuracy
whisper_model = WhisperModel("tiny.en", device="cpu", compute_type="int8")

Base.metadata.create_all(bind=engine)

# ==================================================
# 🔊 VOICE & EMAIL UTILS
# ==================================================
def speak(text):
    print(f"🤖 Bot: {text}")
    try:
        engine_instance = pyttsx3.init()
        engine_instance.setProperty('rate', 145)
        engine_instance.say(text)
        engine_instance.runAndWait()
        engine_instance.stop()
        time.sleep(0.4)
    except Exception as e: print(f"🔊 Voice Error: {e}")

def send_absent_alert(name):
    msg = EmailMessage()
    msg.set_content(f"Participant '{name}' failed to respond after two attempts.")
    msg['Subject'] = f"Meeting Absentee: {name}"
    msg['From'] = SENDER_EMAIL
    msg['To'] = REPORT_EMAIL
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(SENDER_EMAIL, SENDER_PASS)
            smtp.send_message(msg)
    except: pass

# ==================================================
# 🎙️ REAL-TIME WHISPER TRANSCRIPTION
# ==================================================
async def monitor_and_transcribe(participant_name):
    print(f"🎙️ Monitoring {participant_name}...")
    HARDWARE_RATE, MODEL_RATE = 48000, 16000
    DOWNSAMPLE = HARDWARE_RATE // MODEL_RATE
    audio_buffer = []
    talking, last_sound, start_time = False, time.time(), time.time()

    def callback(indata, frames, time_info, status):
        nonlocal talking, last_sound
        raw_data = np.frombuffer(indata, dtype=np.int16)
        audio_float32 = raw_data[::DOWNSAMPLE].astype(np.float32) / 32768.0
        
        with torch.no_grad():
            confidence = vad_model(torch.from_numpy(audio_float32), MODEL_RATE).item()
            if confidence > 0.15:
                talking = True
                last_sound = time.time()
                audio_buffer.append(audio_float32)

    try:
        with sd.RawInputStream(device=V_CABLE_ID, samplerate=HARDWARE_RATE, blocksize=1536, channels=1, dtype='int16', callback=callback):
            while True:
                now = time.time()
                if not talking and (now - start_time) > 12.0: return None
                if talking and (now - last_sound) > 7.0: break
                await asyncio.sleep(0.1)
        
        if audio_buffer:
            print("🧠 Transcribing with Whisper...")
            full_audio = np.concatenate(audio_buffer)
            segments, _ = whisper_model.transcribe(full_audio, beam_size=5)
            transcript = " ".join([s.text for s in segments])
            return transcript
    except Exception as e:
        print(f"❌ Audio Error: {e}")
    return None

# ==================================================
# 🚀 MODERATOR LOOP (RETRY + INTRO + AUTO-GEN)
# ==================================================
async def unified_moderator_loop():
    global LAST_ACTIVITY_TIME
    await IS_MEETING_READY.wait()
    
    # 📢 INTRO SPEECH
    speak("Hello everyone. Please note: This is not a doubt clearing session. This is strictly an update call.")
    speak("Updates must be given verbally. Please do not use the chat box as it will not be recorded.")
    
    finalized = False
    while True:
        db = SessionLocal()
        try:
            learner = db.query(Participant).filter(Participant.status == 'pending').order_by(Participant.joined_at.asc()).first()
            if not learner:
                learner = db.query(Participant).filter(Participant.status == 'retry').order_by(Participant.joined_at.asc()).first()

            if learner:
                LAST_ACTIVITY_TIME = time.time()
                original_status = learner.status
                learner.status = 'processing'; db.commit()

                call_prefix = "Next up is" if original_status == 'pending' else "Second call for"
                speak(f"{call_prefix} {learner.name}. State your update.")
                
                raw_text = await monitor_and_transcribe(learner.name)
                
                if raw_text and len(raw_text.strip()) > 5:
                    learner.status = 'spoken'
                    db.commit()
                    # 💾 Save transcription immediately to MeetingUpdate
                    db.add(MeetingUpdate(name=learner.name, update=raw_text, batch_id="LIVE"))
                    db.commit()
                    speak(f"Thank you {learner.name}.")
                else:
                    if original_status == 'pending':
                        learner.status = 'retry'
                        speak(f"No response. Moving {learner.name} to the end of the queue.")
                    else:
                        learner.status = 'absent'
                        speak(f"No response from {learner.name} after two attempts. Moving on.")
                        send_absent_alert(learner.name)
                    db.commit()
            
            elif (time.time() - LAST_ACTIVITY_TIME) > 60 and not finalized and ACTIVE_MEETING_ID:
                speak("All scheduled updates complete. The session report has been finalized.")
                finalized = True
            
            await asyncio.sleep(5)
        except Exception as e: print(f"❌ Loop Error: {e}"); db.rollback()
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

    if event == "meeting.participant_joined":
        db = SessionLocal()
        name = body.get("payload", {}).get("object", {}).get("participant", {}).get("user_name")
        if name and name.lower() != HOST_NAME.lower():
            if not ACTIVE_MEETING_ID: 
                ACTIVE_MEETING_ID = body.get("payload", {}).get("object", {}).get("id")
                asyncio.get_event_loop().call_later(2, IS_MEETING_READY.set)
            
            exists = db.query(Participant).filter(Participant.name == name, Participant.meeting_id == str(ACTIVE_MEETING_ID)).first()
            if not exists:
                db.add(Participant(name=name, meeting_id=str(ACTIVE_MEETING_ID), status='pending'))
                db.commit()
        db.close()
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)