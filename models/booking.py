from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class BookingBase(BaseModel):
    tour_id: str
    number_of_people: int
    total_price: float

class BookingCreate(BookingBase):
    pass

class BookingResponse(BookingBase):
    id: Optional[str] = None
    user_id: Optional[str] = None
    status: str = "pending"
    created_at: Optional[datetime] = None

class Booking(BookingResponse):
    pass 