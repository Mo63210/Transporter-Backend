from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PickupRequestBase(BaseModel):
    pickup_location: str
    destination: str
    pickup_time: datetime
    number_of_people: int
    preferred_car_type: str
    allow_other_passengers: bool
    special_requests: Optional[str] = None

class PickupRequestCreate(PickupRequestBase):
    pass

class PickupRequestResponse(PickupRequestBase):
    id: Optional[str] = None
    user_id: Optional[str] = None
    status: str = "pending"
    created_at: Optional[datetime] = None

class PickupRequest(PickupRequestResponse):
    pass 