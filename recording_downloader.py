import requests
import os
from zoom_auth import get_zoom_access_token

DOWNLOAD_DIR = "recordings"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def download_recordings(meeting_id, recording_files):
    downloaded_files = []
    access_token = get_zoom_access_token()

    for file in recording_files:
        download_url = file.get("download_url")
        file_type = file.get("file_type")
        recording_type = file.get("recording_type")

        if not download_url:
            continue

        # 🎯 IMPORTANT: Zoom REQUIRES access_token query param
        download_url = f"{download_url}?access_token={access_token}"

        # ✅ Accept BOTH audio + transcript
        if file_type not in ["M4A", "MP3", "VTT"]:
            continue

        filename = f"{meeting_id}_{recording_type}.{file_type.lower()}"
        filepath = os.path.join(DOWNLOAD_DIR, filename)

        r = requests.get(download_url, stream=True)
        if r.status_code == 200:
            with open(filepath, "wb") as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)

            downloaded_files.append(filepath)

    return downloaded_files