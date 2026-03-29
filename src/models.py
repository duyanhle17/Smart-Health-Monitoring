"""
Database models for Heart Rate and Fall detection records.
"""
from sqlalchemy import Column, Integer, Float, String, Boolean, DateTime
from datetime import datetime, timezone

from src.database import Base


class HeartRateRecord(Base):
    __tablename__ = "heart_rate_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    hr = Column(Float, nullable=False)
    rule_status = Column(String, nullable=True)
    rule_message = Column(String, nullable=True)
    is_danger = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class FallRecord(Base):
    __tablename__ = "fall_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    status = Column(String, nullable=False)  # WAITING | SAFE | FALL | RECOVERED
    probability = Column(Float, default=0.0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
