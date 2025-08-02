# bookings.py

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime, timedelta
from typing import List, Optional

# Assuming your models are in a structured directory
from models.booking import BookingCreate, Booking
from models.user import User
from auth.jwt_handler import verify_token

# bookings.py

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime, timedelta
from typing import List, Optional

# Assuming your models are in a structured directory
from models.user import User
from auth.jwt_handler import verify_token

# --- Pydantic Models ---

class BookingCreate(BaseModel):
    tour_id: str
    number_of_people: int
    total_price: float
    payment_type: str

class Booking(BaseModel):
    id: str = Field(alias="_id")
    tour_id: str
    user_id: str
    number_of_people: int
    total_price: float
    status: str
    payment_type: str
    created_at: datetime
    
    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        json_encoders = {ObjectId: str} # Helps with ObjectId conversion

# Models for enriched responses
class TourInfoForBooking(BaseModel):
    id: str = Field(alias="_id")
    from_location: str
    to_location: str
    departure_time: datetime

class DriverInfoForBooking(BaseModel):
    id: str = Field(alias="_id")
    full_name: str
    phone: Optional[str] = None
    rating: float = 0.0
    
class PassengerInfoForBooking(BaseModel):
    id: str = Field(alias="_id")
    full_name: str
    phone: Optional[str] = None

# Add is_rated to the response model
class EnrichedBookingResponse(BaseModel):
    id: str = Field(alias="_id")
    status: str
    total_price: float
    number_of_people: int
    created_at: datetime
    is_rated: Optional[bool] = False # Add this field
    tour: Optional[TourInfoForBooking] = None
    driver: Optional[DriverInfoForBooking] = None
    passenger: Optional[PassengerInfoForBooking] = None

router = APIRouter(prefix="/api/bookings", tags=["bookings"])

# --- Authentication Dependencies ---
async def get_current_user_or_driver(request: Request):
    from fastapi.security import HTTPBearer
    security = HTTPBearer()
    credentials = await security(request)
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication credentials were not provided.")
    
    payload = verify_token(credentials.credentials)
    if not payload or "sub" not in payload or "user_type" not in payload:
        raise HTTPException(status_code=401, detail="Invalid token.")
    
    return payload

async def get_current_user(request: Request, payload: dict = Depends(get_current_user_or_driver)):
    if payload.get("user_type") != "user":
        raise HTTPException(status_code=403, detail="Access forbidden: User role required.")
    
    user_id = payload.get("sub")
    user = await request.app.mongodb["users"].find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user["id"] = str(user["_id"])
    return user

async def get_current_driver(request: Request, payload: dict = Depends(get_current_user_or_driver)):
    if payload.get("user_type") != "driver":
        raise HTTPException(status_code=403, detail="Access forbidden: Driver role required.")

    driver_id = payload.get("sub")
    driver = await request.app.mongodb["drivers"].find_one({"_id": ObjectId(driver_id)})
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found.")
    driver["id"] = str(driver["_id"])
    return driver

router = APIRouter(prefix="/api/bookings", tags=["bookings"])



# --- Booking Endpoints ---

@router.post("/", response_model=Booking)
async def create_booking(booking: BookingCreate, request: Request, current_user: dict = Depends(get_current_user)):
    tour = await request.app.mongodb["tours"].find_one({"_id": ObjectId(booking.tour_id)})
    if not tour:
        raise HTTPException(status_code=404, detail="Tour not found")
    
    if tour["current_capacity"] + booking.number_of_people > tour["max_capacity"]:
        raise HTTPException(status_code=400, detail="Not enough capacity on this tour.")

    driver = await request.app.mongodb["drivers"].find_one({"_id": ObjectId(tour["driver_id"])})

    booking_doc = booking.dict()
    booking_doc["user_id"] = current_user["id"]
    booking_doc["username"] = current_user.get("full_name")
    booking_doc["driver_name"] = driver.get("full_name") if driver else "Unknown Driver"
    
    if booking.payment_type == 'cash':
        booking_doc["status"] = "upcoming"
    else:
        booking_doc["status"] = "paid"
        
    booking_doc["created_at"] = datetime.utcnow()
    
    result = await request.app.mongodb["bookings"].insert_one(booking_doc)
    
    await request.app.mongodb["tours"].update_one(
        {"_id": ObjectId(booking.tour_id)},
        {"$inc": {"current_capacity": booking.number_of_people}}
    )
    
    new_booking = await request.app.mongodb["bookings"].find_one({"_id": result.inserted_id})

    if new_booking:
        new_booking["_id"] = str(new_booking["_id"])

    return new_booking


# --- Authentication Dependencies ---

async def get_current_user_or_driver(request: Request):
    """Generic dependency to get user ID and type from token."""
    from fastapi.security import HTTPBearer
    security = HTTPBearer()
    credentials = await security(request)
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication credentials were not provided.")
    
    payload = verify_token(credentials.credentials)
    if not payload or "sub" not in payload or "user_type" not in payload:
        raise HTTPException(status_code=401, detail="Invalid token.")
    
    return payload

async def get_current_user(request: Request, payload: dict = Depends(get_current_user_or_driver)):
    """Dependency to ensure the authenticated entity is a user."""
    if payload.get("user_type") != "user":
        raise HTTPException(status_code=403, detail="Access forbidden: User role required.")
    
    user_id = payload.get("sub")
    user = await request.app.mongodb["users"].find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user["id"] = str(user["_id"])
    return user

async def get_current_driver(request: Request, payload: dict = Depends(get_current_user_or_driver)):
    """Dependency to ensure the authenticated entity is a driver."""
    if payload.get("user_type") != "driver":
        raise HTTPException(status_code=403, detail="Access forbidden: Driver role required.")

    driver_id = payload.get("sub")
    driver = await request.app.mongodb["drivers"].find_one({"_id": ObjectId(driver_id)})
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found.")
    driver["id"] = str(driver["_id"])
    return driver



@router.get("/my-bookings", response_model=List[EnrichedBookingResponse])
async def get_my_bookings(request: Request, current_user: dict = Depends(get_current_user)):
    """Gets all bookings for the current user, enriched with tour, driver, and rating details."""
    pipeline = [
        {"$match": {"user_id": current_user["id"]}},
        {"$sort": {"created_at": -1}},
        
        # --- THE UPDATE: Add a lookup to the new ratings collection ---
        {"$lookup": {
            "from": "ratings",
            "let": {"booking_id_str": {"$toString": "$_id"}},
            "pipeline": [
                {"$match": {"$expr": {"$eq": ["$booking_id", "$$booking_id_str"]}}}
            ],
            "as": "rating_docs"
        }},
        
        # Join with tours
        {"$addFields": {"tour_object_id": {"$toObjectId": "$tour_id"}}},
        {"$lookup": {"from": "tours", "localField": "tour_object_id", "foreignField": "_id", "as": "tour_details"}},
        {"$unwind": {"path": "$tour_details", "preserveNullAndEmptyArrays": True}},
        
        # Join with drivers
        {"$addFields": {"driver_object_id": {"$toObjectId": "$tour_details.driver_id"}}},
        {"$lookup": {"from": "drivers", "localField": "driver_object_id", "foreignField": "_id", "as": "driver_details"}},
        {"$unwind": {"path": "$driver_details", "preserveNullAndEmptyArrays": True}},
        
        {
            "$project": {
                "_id": {"$toString": "$_id"}, "status": 1, "total_price": 1, "created_at": 1, "number_of_people": 1,
                
                # --- THE UPDATE: Add is_rated field to the response ---
                "is_rated": {"$gt": [{"$size": "$rating_docs"}, 0]},
                
                "tour": {
                    "_id": {"$toString": "$tour_details._id"},
                    "from_location": "$tour_details.from_location",
                    "to_location": "$tour_details.to_location",
                    "departure_time": "$tour_details.departure_time"
                },
                "driver": {
                    "_id": {"$toString": "$driver_details._id"},
                    "full_name": "$driver_details.full_name",
                    "phone": "$driver_details.phone",
                    "rating": "$driver_details.rating",
                    "profile_image": "$driver_details.profile_image" # Pass image to frontend
                }
            }
        }
    ]
    bookings_cursor = request.app.mongodb["bookings"].aggregate(pipeline)
    
    # Add an `is_rated` field to the Pydantic model for validation
    enriched_bookings = await bookings_cursor.to_list(length=100)
    for booking in enriched_bookings:
        booking['id'] = booking['_id'] # Ensure 'id' field for Pydantic
    return enriched_bookings

    

@router.get("/driver-bookings", response_model=List[EnrichedBookingResponse])
async def get_driver_bookings(request: Request, current_driver: dict = Depends(get_current_driver)):
    """Gets all bookings for tours managed by the current driver."""
    tours = await request.app.mongodb["tours"].find({"driver_id": current_driver["id"]}).to_list(length=None)
    tour_ids = [str(tour["_id"]) for tour in tours]

    pipeline = [
        {"$match": {"tour_id": {"$in": tour_ids}}},
        {"$sort": {"created_at": -1}},
        {"$addFields": {"user_object_id": {"$toObjectId": "$user_id"}}},
        {"$lookup": {"from": "users", "localField": "user_object_id", "foreignField": "_id", "as": "passenger_details"}},
        {"$unwind": {"path": "$passenger_details", "preserveNullAndEmptyArrays": True}},
        {"$addFields": {"tour_object_id": {"$toObjectId": "$tour_id"}}},
        {"$lookup": {"from": "tours", "localField": "tour_object_id", "foreignField": "_id", "as": "tour_details"}},
        {"$unwind": {"path": "$tour_details", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "_id": {"$toString": "$_id"}, "status": 1, "total_price": 1, "created_at": 1, "number_of_people": 1,
            "tour": {"_id": {"$toString": "$tour_details._id"}, "from_location": "$tour_details.from_location", "to_location": "$tour_details.to_location", "departure_time": "$tour_details.departure_time"},
            "passenger": {"_id": {"$toString": "$passenger_details._id"}, "full_name": "$passenger_details.full_name", "phone": "$passenger_details.phone"}
        }}
    ]
    bookings_cursor = request.app.mongodb["bookings"].aggregate(pipeline)
    return await bookings_cursor.to_list(length=None)


@router.put("/{booking_id}/cancel", status_code=200)
async def cancel_booking(booking_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Allows a user to cancel their own booking."""
    booking = await request.app.mongodb["bookings"].find_one({"_id": ObjectId(booking_id), "user_id": current_user["id"]})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or access denied.")
    
    # THE UPDATE: Add an explicit check for 'completed' status first for a clearer error message.
    if booking["status"] == "completed":
        raise HTTPException(status_code=400, detail="This ride has already been completed and cannot be cancelled.")
    
    # This existing check will now handle other non-cancellable statuses (e.g., already 'cancelled')
    if booking["status"] not in ["paid", "upcoming"]:
        raise HTTPException(status_code=400, detail=f"Cannot cancel a booking with status '{booking['status']}'.")
    
    # --- The rest of the function remains the same ---
    await request.app.mongodb["bookings"].update_one(
        {"_id": ObjectId(booking_id)}, 
        {"$set": {"status": "cancelled"}}
    )
    
    await request.app.mongodb["tours"].update_one(
        {"_id": ObjectId(booking["tour_id"])},
        {"$inc": {"current_capacity": -booking["number_of_people"]}}
    )
    
    return {"message": "Booking cancelled successfully"}



@router.put("/{booking_id}/complete", status_code=200)
async def complete_booking(booking_id: str, request: Request, current_driver: dict = Depends(get_current_driver)):
    """Allows the assigned driver to mark a booking as completed."""
    
    # 1. Find the booking
    booking = await request.app.mongodb["bookings"].find_one({"_id": ObjectId(booking_id)})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # 2. Find the tour associated with the booking to verify the driver
    tour = await request.app.mongodb["tours"].find_one({"_id": ObjectId(booking["tour_id"])})
    
    # 3. Authorize: Ensure the logged-in driver is the one assigned to this tour
    if not tour or tour.get("driver_id") != current_driver["id"]:
        raise HTTPException(status_code=403, detail="Access forbidden: You are not the driver for this tour.")

    # 4. Validate status: Only upcoming or paid bookings can be completed
    if booking["status"] not in ["paid", "upcoming"]:
        raise HTTPException(status_code=400, detail=f"Cannot complete a booking with status '{booking['status']}'.")

    # 5. Update the booking status to "completed"
    await request.app.mongodb["bookings"].update_one(
        {"_id": ObjectId(booking_id)},
        {"$set": {"status": "completed"}}
    )
    
    return {"message": "Booking marked as completed successfully"}


