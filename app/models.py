from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String, index=True)  # sora, veo3
    email = Column(String, unique=True, index=True)
    password = Column(String) # Encrypted ideally, but plain for local MVP
    proxy = Column(String, nullable=True) # format: ip:port:user:pass
    
    status = Column(String, default="live") # live, die, cooldown, limit_reached
    cookies = Column(JSON, nullable=True) # Store cookies/session
    last_used = Column(DateTime(timezone=True), nullable=True)
    
    # Credit tracking
    credits_remaining = Column(Integer, default=0)
    credits_last_checked = Column(DateTime(timezone=True), nullable=True)
    
    jobs = relationship("Job", back_populates="account")

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    prompt = Column(Text)
    image_path = Column(String, nullable=True)
    
    # Settings for this specific job
    duration = Column(Integer, default=5) # seconds
    aspect_ratio = Column(String, default="16:9")
    
    status = Column(String, default="pending") # pending, processing, completed, failed
    error_message = Column(Text, nullable=True)
    
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    
    video_url = Column(String, nullable=True)
    task_state = Column(Text, nullable=True)  # JSON: track task progress
    local_path = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    account = relationship("Account", back_populates="jobs")

class Setting(Base):
    __tablename__ = "settings"
    
    key = Column(String, primary_key=True, index=True)
    value = Column(String)
