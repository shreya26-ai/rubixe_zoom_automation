import asyncio
from queue_manager import get_queue

# 🔴 GLOBAL CONTROL FLAGS
meeting_ready_event = asyncio.Event()
speaker_done_event = asyncio.Event()
current_speaker = None

async def process_queue_safely(announce_callback):
    global current_speaker

    print("🤖 AI Queue Processor Running (Waiting for meeting readiness)")

    # 🕒 WAIT until meeting warm-up is complete
    await meeting_ready_event.wait()
    print("✅ Meeting warm-up completed. AI starting announcements.")

    while True:
        queue = list(get_queue())

        if not queue:
            await asyncio.sleep(1)
            continue

        current_speaker = queue[0]

        print(f"🎙️ AI CALLING → {current_speaker}")
        await announce_callback(current_speaker)

        # 🔒 WAIT until participant leaves meeting
        speaker_done_event.clear()
        await speaker_done_event.wait()

        print(f"✅ Speaker finished → {current_speaker}")
        current_speaker = None