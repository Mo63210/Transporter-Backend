from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

class DriverBase(BaseModel):
    email: EmailStr
    full_name: str
    phone: str
    car_type: str
    license_number: str
    working_area: str

class DriverCreate(DriverBase):
    password: str

class DriverLogin(BaseModel):
    email: EmailStr
    password: str

class DriverResponse(DriverBase):
    id: Optional[str] = None
    rating: float = 0.0
    total_trips: int = 0
    portfolio_completed: bool = False
    created_at: Optional[datetime] = None

class Driver(DriverResponse):
    password: str

class DriverPortfolio(BaseModel):
    driver_id: Optional[str] = None
    profile_image: Optional[str] = None
    age: int
    car_model: str
    car_year: int
    car_color: str
    experience_years: int
    bio: str
    languages: List[str] = []
    certifications: List[str] = []
    updated_at: Optional[datetime] = None 