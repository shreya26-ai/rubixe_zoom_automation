from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime, timezone
from database import Base

class Participant(Base):
    """Used for the live meeting queue (Phase 1)"""
    __tablename__ = "participants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    meeting_id = Column(String)
    # Statuses: 'pending', 'processing', 'spoken', 'absent', 'expired'
    status = Column(String, default="pending")
    attempts = Column(Integer, default=0)
    zoom_user_id = Column(String, nullable=True) 
    joined_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class MeetingUpdate(Base):
    """Used for storing AI-extracted results from transcripts (Phase 2)"""
    __tablename__ = "meeting_updates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    batch_id = Column(String)
    update = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))