import pyttsx3

print("🔊 Starting voice test...")
try:
    e = pyttsx3.init()
    # Set a slower rate so you can hear clarity
    e.setProperty('rate', 130) 
    e.say("The voice engine is working. I am ready for the meeting.")
    e.runAndWait()
    print("✅ Test complete. If you heard the bot, your audio is working.")
except Exception as e:
    print(f"❌ Error: {e}")