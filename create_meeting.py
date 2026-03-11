import requests
from zoom_auth import get_zoom_access_token
from datetime import datetime, timedelta

def create_saturday_meeting():
    access_token = get_zoom_access_token()

    url = "https://api.zoom.us/v2/users/me/meetings"

    # Calculate next Saturday
    today = datetime.now()
    days_until_saturday = (5 - today.weekday()) % 7
    saturday = today + timedelta(days=days_until_saturday)

    meeting_payload = {
        "topic": "Weekly AI Automated Status Call",
        "type": 2,  # Scheduled meeting
        "start_time": saturday.strftime("%Y-%m-%dT10:00:00"),
        "duration": 120,
        "timezone": "Asia/Kolkata",
        "settings": {
            "host_video": True,
            "participant_video": False,
            "mute_upon_entry": True,
            "waiting_room": True,
            "auto_recording": "cloud",
            "approval_type": 0
        }
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    response = requests.post(url, headers=headers, json=meeting_payload)

    if response.status_code == 201:
        meeting = response.json()
        print("✅ Zoom Meeting Created Successfully")
        print("Meeting ID:", meeting["id"])
        print("Join URL:", meeting["join_url"])
    else:
        print("❌ Failed to create meeting")
        print(response.text)

if __name__ == "__main__":
    create_saturday_meeting()
