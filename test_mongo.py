from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["zoom_reports"]
collection = db["weekly_reports"]

# Test insert
collection.insert_one({
    "participant_name": "TestUser",
    "batch_id": "AI-DS-999",
    "weekly_work": "Testing MongoDB connection locally",
    "confidence": 0.99,
    "meeting_id": "TEST_MEETING_999"
})

print("✅ Inserted test document successfully!")
