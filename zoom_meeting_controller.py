import requests
from zoom_auth import get_zoom_access_token

def end_zoom_meeting(meeting_id):
    access_token = get_zoom_access_token()

    url = f"https://api.zoom.us/v2/meetings/{meeting_id}/status"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "action": "end"
    }

    response = requests.put(url, headers=headers, json=payload)

    if response.status_code == 204:
        print(f"🛑 Zoom Meeting {meeting_id} ended successfully")
    else:
        print("❌ Failed to end Zoom meeting")
        print(response.text)
