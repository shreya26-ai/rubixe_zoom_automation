import threading
import time
from queue_manager import add_participant, get_queue
from ai_moderator import run_ai_moderator

def queue_manager_cli():
    print("
--- 📝 Participant Queue Manager ---")
    print("Commands: 'add <name>', 'list', 'quit'")
    while True:
        try:
            cmd = input("> ").strip().split(" ", 1)
            if not cmd: continue
            
            action = cmd[0].lower()
            if action == "add" and len(cmd) > 1:
                name = cmd[1]
                add_participant(name)
                print(f"✅ Added {name} to queue.")
            elif action == "list":
                print(f"Current Queue: {get_queue()}")
            elif action == "quit":
                print("Exiting CLI...")
                break
            else:
                print("Unknown command.")
        except KeyboardInterrupt:
            break

if __name__ == "__main__":
    print("🎯 Starting Real-Time Zoom AI Test")
    print("1. Make sure your microphone and speakers are set correctly.")
    print("2. Join your Zoom meeting.")
    
    # Start Moderator in a background thread
    moderator_thread = threading.Thread(target=run_ai_moderator, daemon=True)
    moderator_thread.start()
    
    # Start CLI in main thread
    queue_manager_cli()
