import time
import numpy as np
import sounddevice as sd
import pyttsx3
from queue_manager import get_queue

# Configuration
RATE = 44100
SILENCE_THRESHOLD = 500  # Adjust based on your mic sensitivity
engine = pyttsx3.init()

def is_someone_talking(duration=1.0, threshold=500):
    """
    Checks if there is sound above the threshold for a 1-second window.
    """
    frames = []
    def callback(indata, frames, time, status):
        frames.append(np.linalg.norm(indata))

    try:
        with sd.InputStream(callback=callback, channels=1, samplerate=RATE):
            sd.sleep(int(duration * 1000))
    except Exception as e:
        print(f"Error accessing microphone: {e}")
        return False
    
    avg_volume = np.mean(frames) if frames else 0
    return avg_volume > threshold

def wait_for_completion(participant_name):
    """
    Stays in a loop as long as sound is detected. 
    Ends only after 3 seconds of continuous silence.
    """
    print(f"👂 Listening to {participant_name}...")
    silence_counter = 0
    max_silence = 3  # Seconds of silence allowed before moving on
    
    while True:
        if is_someone_talking(threshold=SILENCE_THRESHOLD):
            silence_counter = 0
            print(f"🎙️ {participant_name} is speaking...", end="\r")
        else:
            silence_counter += 1
            print(f"😶 Silence detected ({silence_counter}/{max_silence}s)", end="\r")
        
        if silence_counter >= max_silence:
            print(f"\n✅ {participant_name} appears to have finished.")
            break
            
        time.sleep(0.1)

def run_ai_moderator():
    print("🚀 AI Moderator Started. Looking for participants in queue...")
    while True:
        queue = get_queue()
        if not queue:
            print("😴 Queue is empty. Waiting...", end="\r")
            time.sleep(2)
            continue

        for participant in queue:
            print(f"\n📢 Calling on {participant}")
            # 1. Announce
            msg = f"Next up is {participant}. Please state your update."
            engine.say(msg)
            engine.runAndWait() 
            
            # 2. Use the smart listener
            wait_for_completion(participant)
            
            # 3. Speak the closing sentence
            engine.say(f"Thank you {participant}. Update received.")
            engine.runAndWait()
            
            # Remove from queue after processing (optional, depends on your logic)
            from queue_manager import remove_participant
            remove_participant(participant)
            
        time.sleep(1)

if __name__ == "__main__":
    try:
        run_ai_moderator()
    except KeyboardInterrupt:
        print("\n👋 AI Moderator stopped.")
    finally:
        engine.stop()
