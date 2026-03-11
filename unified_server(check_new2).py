import hashlib, hmac, asyncio, os, time, datetime, re, requests, json
import uvicorn, numpy as np, sounddevice as sd, torch, edge_tts, pygame
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
HOST_NAME = "Ashok" #
V_CABLE_ID = 1           

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
Base.metadata.create_all(bind=engine)
model, _ = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad', force_reload=False, onnx=True)

# ==================================================
# 🧹 DATABASE CLEANUP
# ==================================================
def clear_db():
    print("🧹 Cleaning database for new session...")
    db = SessionLocal()
    try:
        db.execute(text("TRUNCATE TABLE participants, meeting_updates RESTART IDENTITY;"))
        db.commit()
        print("✅ Database cleared successfully.")
    except Exception as e: print(f"⚠️ DB Clear Error: {e}")
    finally: db.close()

# ==================================================
# 🔑 ZOOM API ENGINE (MUTING CONTROL)
# ==================================================
async def get_zoom_token():
    url = f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={os.getenv('ZOOM_ACCOUNT_ID')}"
    auth = (os.getenv('ZOOM_CLIENT_ID'), os.getenv('ZOOM_CLIENT_SECRET'))
    response = requests.post(url, auth=auth)
    return response.json().get("access_token")

# 🔊 Send a "Request to Unmute" to the specific person
async def ask_to_unmute(meeting_id, zoom_user_id):
    token = await get_zoom_token()
    url = f"https://api.zoom.us/v2/meetings/{meeting_id}/members/{zoom_user_id}/status"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    # 'action': 'unmute' sends a prompt to the user's screen
    payload = {"action": "unmute"} 
    requests.patch(url, json=payload, headers=headers)
    print(f"📩 Sent Unmute Request to: {zoom_user_id}")

# 🔇 Force Mute when silence is detected
async def force_mute(meeting_id, zoom_user_id):
    token = await get_zoom_token()
    url = f"https://api.zoom.us/v2/meetings/{meeting_id}/members/{zoom_user_id}/status"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"mute_audio": True}
    requests.patch(url, json=payload, headers=headers)
    print(f"🔒 Silenced/Muted: {zoom_user_id}")

# ==================================================
# 🔊 PROFESSIONAL VOICE (EDGE-TTS)
# ==================================================
async def speak(text_to_say):
    print(f"🤖 Bot: {text_to_say}")
    communicate = edge_tts.Communicate(text_to_say, "en-IN-NeerjaNeural")
    await communicate.save("temp_speech.mp3")
    
    pygame.mixer.init()
    pygame.mixer.music.load("temp_speech.mp3")
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        await asyncio.sleep(0.1)
    pygame.mixer.quit()
    if os.path.exists("temp_speech.mp3"): os.remove("temp_speech.mp3")

# ==================================================
# 🎙️ AUDIO MONITORING (VAD)
# ==================================================
async def monitor_speech_local(participant_name):
    print(f"🎙️ Monitoring {participant_name}...")
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
                if not talking: print(f"💬 [LIVE] {participant_name} speaking...")
                talking = True; last_sound = time.time()

    try:
        with sd.RawInputStream(device=V_CABLE_ID, samplerate=HARDWARE_RATE, blocksize=1536, channels=1, dtype='int16', callback=callback):
            while True:
                now = time.time()
                if not talking and (now - start_time) > 12.0: return False 
                if talking and (now - last_sound) > 7.0: return True      
                await asyncio.sleep(0.1)
    except: return False

# ==================================================
# ✨ TRANSCRIPT EXTRACTION
# ==================================================
async def process_transcript_task(url, token):
    print("⚡ Extracting updates...")
    db = SessionLocal()
    try:
        official_names = [p.name for p in db.query(Participant).filter(Participant.meeting_id == str(ACTIVE_MEETING_ID)).all()]
        name_list_str = ", ".join(official_names)
        response = requests.get(f"{url}?access_token={token}")
        if response.status_code == 200:
            raw_vtt = response.text
            clean_text = re.sub(r'(\d{2}:\d{2}:\d{2}\.\d{3} --> .*?\n)|(WEBVTT\n)|(^\d+\n)', '', raw_vtt, flags=re.MULTILINE)
            clean_text = re.sub(r'^(Ashok|Bot|🤖 Bot):.*$', '', clean_text, flags=re.MULTILINE)
            
            prompt = f"Official Names: {name_list_str}. Extract JSON: {{\"updates\": [{{\"name\": \"Official Name\", \"batch_id\": \"ID\", \"update\": \"Desc\"}}]}} Transcript: {clean_text}"
            completion = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "system", "content": "Return ONLY JSON."}, {"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            updates = json.loads(completion.choices[0].message.content).get("updates", [])
            for item in updates:
                db.add(MeetingUpdate(name=item.get("name"), batch_id=str(item.get("batch_id")), update=item.get("update")))
            db.commit()
            print(f"💾 Database Updated. ({len(updates)} entries)")
    except Exception as e: print(f"❌ Transcript Error: {e}")
    finally: db.close()

# 🔇 1. Mute Everyone (Locks the meeting down)
async def mute_all_participants(meeting_id):
    token = await get_zoom_token()
    url = f"https://api.zoom.us/v2/meetings/{meeting_id}/events"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    # This prevents participants from unmuting themselves manually
    payload = {"method": "participant.mute_all", "params": {"allow_unmute": False}} 
    response = requests.patch(url, json=payload, headers=headers)
    print(f"🔒 Meeting Locked: {response.status_code}")

# 📩 2. Permission to Speak (Sends the pop-up to one person)
async def ask_to_unmute(meeting_id, zoom_user_id):
    token = await get_zoom_token()
    url = f"https://api.zoom.us/v2/meetings/{meeting_id}/members/{zoom_user_id}/status"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"action": "unmute"} 
    requests.patch(url, json=payload, headers=headers)
    print(f"📩 Unmute request sent to: {zoom_user_id}")

# 🔒 3. Re-Mute (Closes the mic after silence is detected)
async def force_mute(meeting_id, zoom_user_id):
    token = await get_zoom_token()
    url = f"https://api.zoom.us/v2/meetings/{meeting_id}/members/{zoom_user_id}/status"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"mute_audio": True}
    requests.patch(url, json=payload, headers=headers)
    print(f"🔇 User re-muted: {zoom_user_id}")
    
# ==================================================
# 🚀 MODERATOR LOOP (PERMISSION-BASED UNMUTING)
# ==================================================
async def unified_moderator_loop():
    print("⏳ Waiting for Zoom Webhook to start meeting...")
    await IS_MEETING_READY.wait()
    
    # Live status snapshots during 60s settle period
    for i in range(4):
        db = SessionLocal()
        pending_count = db.query(Participant).filter(
            Participant.status == 'pending', 
            Participant.meeting_id == str(ACTIVE_MEETING_ID)
        ).count()
        db.close()
        print(f"⏳ Settle period ({60 - (i*15)}s remaining) | Currently in Queue: {pending_count}")
        await asyncio.sleep(15)

    print("🚀 Moderator Loop Active!")
    await speak("Hello everyone. This is strictly an update call. Updates must be given verbally.")
    
    # Start by muting everyone to establish control
    await mute_all_participants(ACTIVE_MEETING_ID)
    
    empty_queue_counter = 0

    while True:
        db = SessionLocal()
        try:
            # 1. Fetch next person in queue
            learner = db.query(Participant).filter(
                Participant.status == 'pending', 
                Participant.meeting_id == str(ACTIVE_MEETING_ID)
            ).order_by(Participant.joined_at.asc()).first()
            
            if not learner:
                learner = db.query(Participant).filter(
                    Participant.status == 'retry', 
                    Participant.meeting_id == str(ACTIVE_MEETING_ID)
                ).order_by(Participant.joined_at.asc()).first()

            if learner:
                empty_queue_counter = 0 
                status = learner.status
                learner.status = 'processing'; db.commit()
                
                msg = f"{'Next' if status == 'pending' else 'Second call'} for {learner.name}. Please unmute and state your update."
                await speak(msg)
                
                # 📩 Send the "Ask to Unmute" prompt to their screen
                if learner.zoom_user_id:
                    await ask_to_unmute(ACTIVE_MEETING_ID, learner.zoom_user_id)
                
                # 🎙️ VAD Monitoring: Detects when they start and stop talking
                if await monitor_speech_local(learner.name):
                    learner.status = 'spoken'
                    
                    # 🔒 Silence detected! Force mute them back immediately
                    if learner.zoom_user_id:
                        await force_mute(ACTIVE_MEETING_ID, learner.zoom_user_id)
                    
                    await speak(f"Thank you {learner.name}.")
                else:
                    learner.status = 'retry' if status == 'pending' else 'absent'
                    
                    # 🔒 Mute them if they timed out/never spoke
                    if learner.zoom_user_id:
                        await force_mute(ACTIVE_MEETING_ID, learner.zoom_user_id)
                        
                    await speak("Moving to end of queue." if learner.status == 'retry' else "Moving on.")
                
                db.commit()
            else:
                # 🏁 End Logic: Check for 30s of actual silence
                empty_queue_counter += 5
                if empty_queue_counter >= 30:
                    await speak("Everyone has been called. Meeting complete. You may end the call.")
                    print("✅ Meeting finished. Staying alive for transcript webhook...")
                    empty_queue_counter = -99999 
                elif empty_queue_counter > 0:
                    print(f"🏁 Queue appears empty. Final check in {30 - empty_queue_counter}s...")

            await asyncio.sleep(5)
        except Exception as e: 
            print(f"❌ Loop Error: {e}")
            db.rollback()
        finally: 
            db.close()

# ==================================================
# ⚡ FASTAPI WEBHOOK (WITH CRC & ZOOM_ID)
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

    # 🛡️ URL Validation Handshake
    if event == "endpoint.url_validation":
        plain_token = body.get("payload", {}).get("plainToken")
        secret = os.getenv("ZOOM_WEBHOOK_SECRET").encode('utf-8')
        hash_val = hmac.new(secret, plain_token.encode('utf-8'), hashlib.sha256).hexdigest()
        return {"plainToken": plain_token, "encryptedToken": hash_val}

    if event == "meeting.participant_joined":
        p_obj = body.get("payload", {}).get("object", {})
        p_id = p_obj.get("id")
        participant = p_obj.get("participant", {})
        name = participant.get("user_name")
        z_id = participant.get("user_id") #

        if name and name.lower() == HOST_NAME.lower(): return {"status": "ok"}

        if ACTIVE_MEETING_ID is None:
            ACTIVE_MEETING_ID = p_id; IS_MEETING_READY.set()
        elif ACTIVE_MEETING_ID != p_id:
            ACTIVE_MEETING_ID = p_id; SEEN_PARTICIPANTS.clear()

        if name and name not in SEEN_PARTICIPANTS:
            db = SessionLocal()
            exists = db.query(Participant).filter(Participant.name == name, Participant.meeting_id == str(ACTIVE_MEETING_ID)).first()
            if not exists:
                db.add(Participant(name=name, meeting_id=str(ACTIVE_MEETING_ID), status='pending', zoom_user_id=z_id))
                db.commit(); SEEN_PARTICIPANTS.add(name)
            db.close()

    if event == "recording.transcript_completed":
        payload = body.get("payload", {}).get("object", {})
        file = next((f for f in payload.get("recording_files", []) if f.get("file_type") == "TRANSCRIPT"), None)
        if file: asyncio.create_task(process_transcript_task(file.get("download_url"), body.get("download_token")))

    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)