import re

def extract_batch_and_work(text):
    batch_pattern = r"[A-Z]{2,}-[A-Z]{2,}-\d{2,}"
    batch_match = re.search(batch_pattern, text)

    batch_id = batch_match.group() if batch_match else "UNKNOWN"

    work_summary = text.replace(batch_id, "").strip()

    confidence = 0.95 if batch_id != "UNKNOWN" else 0.7

    return {
        "batch_id": batch_id,
        "weekly_work": work_summary,
        "confidence": confidence
    }
