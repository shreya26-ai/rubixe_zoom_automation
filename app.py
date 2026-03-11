from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/zoom/webhook")
async def zoom_webhook(request: Request):
    payload = await request.json()
    event = payload.get("event")

    if event == "recording.completed":
        meeting_id = payload["payload"]["object"]["id"]
        print(f"🎥 Recording completed for meeting ID: {meeting_id}")

    return {"status": "ok"}
