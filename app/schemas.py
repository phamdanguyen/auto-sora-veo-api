from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

# --- Account Schemas ---
class AccountBase(BaseModel):
    platform: str
    email: str
    proxy: Optional[str] = None

class AccountCreate(AccountBase):
    password: Optional[str] = None

class AccountUpdate(AccountBase):
    status: Optional[str] = None
    cookies: Optional[Dict[str, Any]] = None

class Account(AccountBase):
    id: int
    status: str
    last_used: Optional[datetime] = None
    credits_remaining: Optional[int] = None
    credits_last_checked: Optional[datetime] = None

    class Config:
        orm_mode = True

# --- Job Schemas ---
class JobBase(BaseModel):
    prompt: str
    image_path: Optional[str] = None
    duration: int = 5
    aspect_ratio: str = "16:9"

class JobCreate(JobBase):
    pass

class JobUpdate(BaseModel):
    prompt: Optional[str] = None
    duration: Optional[int] = None
    aspect_ratio: Optional[str] = None


class Job(JobBase):
    id: int
    status: str
    error_message: Optional[str] = None
    video_url: Optional[str] = None
    task_state: Optional[str] = None  # JSON string
    local_path: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    account_id: Optional[int] = None
    account: Optional[Account] = None

    class Config:
        orm_mode = True
