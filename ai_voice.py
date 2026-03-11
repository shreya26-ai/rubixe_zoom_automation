import os
from gtts import gTTS
import playsound
import uuid

def speak(text: str):
    # ✅ Use system temp directory
    temp_dir = os.path.join(os.getcwd(), "temp_audio")
    os.makedirs(temp_dir, exist_ok=True)

    filename = os.path.join(
        temp_dir,
        f"speech_{uuid.uuid4().hex}.mp3"
    )

    tts = gTTS(text=text, lang="en")
    tts.save(filename)

    playsound.playsound(filename)

    # Optional cleanup
    try:
        os.remove(filename)
    except:
        pass
