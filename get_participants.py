import requests
from zoom_auth import get_zoom_access_token

MEETING_ID = "85394762118"

def get_participants():
    token = get_zoom_access_token()

    # ✅ CHANGE: Use the dashboard metrics endpoint for LIVE meetings
    url = f"https://api.zoom.us/v2/metrics/meetings/{MEETING_ID}/participants"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Optional: Add query params if the meeting has more than 30 people
    params = {"page_size": 100}

    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        participants = response.json().get("participants", [])
        if not participants:
            print("🤖 No participants found in the live dashboard.")
        else:
            print(f"👥 Participants currently in meeting ({len(participants)}):")
            for p in participants:
                # Note: Dashboard API uses 'user_name' instead of 'name'
                print(f"- {p.get('user_name', 'Unknown')} | Joined: {p.get('join_time')}")
    elif response.status_code == 404:
        print("❌ Meeting not found or is not currently active.")
    else:
        print(f"❌ Error {response.status_code}: {response.text}")

if __name__ == "__main__":
    get_participants()