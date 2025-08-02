# routers/tours.py

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from typing import List, Optional
from auth.jwt_handler import verify_token
from fastapi.security import HTTPBearer

# Adjust import paths as needed
from pickup.pickup import get_current_driver

router = APIRouter(prefix="/api/tours", tags=["tours"])

# --- Pydantic Models ---
class DriverInfoForTour(BaseModel):
    id: str = Field(alias="_id")
    full_name: str
    rating: float = 0.0
    total_trips: int = 0
    car_type: Optional[str] = None
    phone: Optional[str] = None
    class Config:
        allow_population_by_field_name = True

class TourResponse(BaseModel):
    id: str = Field(alias="_id")
    from_location: str
    to_location: str
    departure_time: datetime
    return_time: Optional[datetime] = None
    max_capacity: int
    price_per_person: float
    description: str
    driver_id: str
    current_capacity: int
    status: str
    created_at: datetime
    driver: Optional[DriverInfoForTour] = None
    class Config:
        allow_population_by_field_name = True

class TourCreate(BaseModel):
    from_location: str
    to_location: str
    departure_time: datetime
    return_time: Optional[datetime] = None
    max_capacity: int
    price_per_person: float
    description: str

# --- Endpoints ---

@router.post("/", response_model=TourResponse)
async def create_tour(tour: TourCreate, request: Request, current_driver: dict = Depends(get_current_driver)):
    """Allows a driver to create a new tour."""
    db = request.app.mongodb
    tour_doc = tour.dict()
    tour_doc["driver_id"] = current_driver["id"]
    tour_doc["current_capacity"] = 0
    tour_doc["status"] = "active"
    tour_doc["created_at"] = datetime.utcnow()

    result = await db["tours"].insert_one(tour_doc)
    new_tour = await db["tours"].find_one({"_id": result.inserted_id})

    if new_tour:
        # ✅ FIX: Prepare the document fully before returning to match the response model
        new_tour["_id"] = str(new_tour["_id"])
        driver_details = current_driver
        driver_details["_id"] = str(driver_details["_id"])
        
        new_tour["driver"] = driver_details
        return new_tour

    raise HTTPException(status_code=500, detail="Failed to create tour.")


async def get_optional_current_user(request: Request):
    """Tries to get the current user, but does not fail if no token is provided."""
    try:
        security = HTTPBearer(auto_error=False)
        credentials = await security(request)
        if credentials:
            payload = verify_token(credentials.credentials)
            if payload and payload.get("user_type") == "user":
                user_id = payload.get("sub")
                user = await request.app.mongodb["users"].find_one({"_id": ObjectId(user_id)})
                if user:
                    user["id"] = str(user["_id"])
                    return user
    except Exception:
        return None # Fail silently on any error
    return None

@router.get("/", response_model=List[TourResponse])
async def get_tours(
    request: Request,
    from_location: Optional[str] = None,
    to_location: Optional[str] = None,
    max_price: Optional[float] = None,
    date: Optional[str] = None,
    current_user: Optional[dict] = Depends(get_optional_current_user)
):
    """
    Fetches all active tours, prioritizing tours from drivers with fewer tours.
    """
    db = request.app.mongodb
    
    pipeline = []
    
    # --- THE UPDATE: Filter out tours the user has already booked ---
    booked_tour_ids = []
    if current_user:
        user_bookings = await db["bookings"].find(
            {"user_id": current_user["id"], "status": {"$ne": "cancelled"}},
            {"tour_id": 1}
        ).to_list(length=None)
        booked_tour_ids = [ObjectId(b["tour_id"]) for b in user_bookings]

    match_filter = {
        "status": "active",
        "$expr": {"$lt": ["$current_capacity", "$max_capacity"]},
    }
    # Add the filter to exclude booked tours if the list is not empty
    if booked_tour_ids:
        match_filter["_id"] = {"$nin": booked_tour_ids}

    # --- The rest of the filtering logic remains the same ---
    if from_location:
        match_filter["from_location"] = {"$regex": from_location, "$options": "i"}
    if to_location:
        match_filter["to_location"] = {"$regex": to_location, "$options": "i"}
    if max_price:
        match_filter["price_per_person"] = {"$lte": float(max_price)}
    if date:
        try:
            match_filter["departure_time"] = {"$gte": datetime.fromisoformat(date)}
        except Exception:
            pass 
    
    pipeline.append({"$match": match_filter})
    pipeline.append({"$sort": {"created_at": -1}})
    
    # --- THE UPDATE: Complete new aggregation pipeline with prioritized sorting ---
    pipeline = [
        # Stage 1: Initial match for active, available tours
        {"$match": match_filter},
        
        # Stage 2: Join with the drivers collection to get driver details
        {"$addFields": {"driver_object_id": {"$toObjectId": "$driver_id"}}},
        {"$lookup": {
            "from": "drivers",
            "localField": "driver_object_id",
            "foreignField": "_id",
            "as": "driver_details"
        }},
        {"$unwind": {"path": "$driver_details", "preserveNullAndEmptyArrays": True}},

        # Stage 3: Sort by driver's tour count (ascending) and then by tour creation date (descending)
        {"$sort": {
            "driver_details.tour_count": 1, # Drivers with fewer tours appear first
            "created_at": -1                # Newest tours from those drivers appear first
        }},
        
        # Stage 4: Project the final shape of the response document
        {"$project": {
            "_id": {"$toString": "$_id"},
            "from_location": 1, "to_location": 1, "departure_time": 1, "return_time": 1,
            "max_capacity": 1, "price_per_person": 1, "description": 1, "driver_id": 1,
            "current_capacity": 1, "status": 1, "created_at": 1,
            "driver": {
                "_id": {"$toString": "$driver_details._id"},
                "full_name": "$driver_details.full_name",
                "rating": "$driver_details.rating",
                "car_type": "$driver_details.car_type",
                "phone": "$driver_details.phone",
                "total_trips": "$driver_details.total_trips",
                "profile_image": "$driver_details.profile_image",
                "tour_count": "$driver_details.tour_count" # Include tour_count in response
            }
        }}
    ]
    
    tours = await db["tours"].aggregate(pipeline).to_list(length=100)
    return tours

@router.get("/{tour_id}", response_model=TourResponse)
async def get_tour(tour_id: str, request: Request):
    """Fetches a single tour using an efficient aggregation pipeline."""

    if not ObjectId.is_valid(tour_id):
        raise HTTPException(status_code=400, detail="Invalid tour ID format.")
    
    pipeline = [
            {"$match": {"_id": ObjectId(tour_id)}},
            {"$limit": 1},
            {"$addFields": {"driver_object_id": {"$toObjectId": "$driver_id"}}},
            {"$lookup": { "from": "drivers", "localField": "driver_object_id", "foreignField": "_id", "as": "driver_details" }},
            {"$unwind": {"path": "$driver_details", "preserveNullAndEmptyArrays": True}},
            {"$project": {
                "_id": {"$toString": "$_id"},
                "from_location": 1, "to_location": 1, "departure_time": 1, "return_time": 1,
                "max_capacity": 1, "price_per_person": 1, "description": 1, "driver_id": 1,
                "current_capacity": 1, "status": 1, "created_at": 1,
                "driver": {
                    "_id": {"$toString": "$driver_details._id"},
                    "full_name": "$driver_details.full_name", "rating": "$driver_details.rating",
                    "car_type": "$driver_details.car_type", "phone": "$driver_details.phone",
                    "total_trips": "$driver_details.total_trips", "profile_image": "$driver_details.profile_image"
                }
            }}
        ]

    result = await request.app.mongodb["tours"].aggregate(pipeline).to_list(length=1)
    if not result:
        raise HTTPException(status_code=404, detail="Tour not found")
    
    return result[0]