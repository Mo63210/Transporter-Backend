from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class RatingBase(BaseModel):
    rating: float
    comment: Optional[str] = None

class RatingCreate(RatingBase):
    target_id: str  # ID of the user/driver being rated
    target_type: str  # "user" or "driver"
    booking_id: Optional[str] = None  # Optional booking reference

class RatingResponse(RatingBase):
    id: Optional[str] = None
    user_id: Optional[str] = None
    target_id: Optional[str] = None
    target_type: Optional[str] = None
    booking_id: Optional[str] = None
    created_at: Optional[datetime] = None

class Rating(RatingResponse):
    pass 