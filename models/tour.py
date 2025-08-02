from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class TourBase(BaseModel):
    from_location: str
    to_location: str
    departure_time: datetime
    return_time: Optional[datetime] = None
    max_capacity: int
    price_per_person: float
    description: Optional[str] = None

class TourCreate(TourBase):
    pass

class TourResponse(TourBase):
    id: Optional[str] = None
    driver_id: Optional[str] = None
    current_capacity: int = 0
    status: str = "active"
    created_at: Optional[datetime] = None

class Tour(TourResponse):
    pass

class TourBooking(BaseModel):
    tour_id: str
    user_id: str
    number_of_people: int
    total_price: float
    status: str = "pending"
    created_at: Optional[datetime] = None 