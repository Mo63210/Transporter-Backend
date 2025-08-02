from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class NotificationBase(BaseModel):
    title: str
    message: str
    notification_type: str  # "booking", "pickup", "rating", "system"

class NotificationCreate(NotificationBase):
    recipient_id: str
    recipient_type: str  # "user" or "driver"

class NotificationResponse(NotificationBase):
    id: Optional[str] = None
    recipient_id: Optional[str] = None
    recipient_type: Optional[str] = None
    read: bool = False
    created_at: Optional[datetime] = None

class Notification(NotificationResponse):
    pass 