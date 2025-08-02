# drivers.py

from fastapi import APIRouter, Depends, HTTPException, Request
from datetime import date, datetime
from typing import Optional, List, Union
from bson import ObjectId
from pickup.pickup import get_current_user 
from pydantic import BaseModel, Field, validator

# Assuming these models are in a 'models' directory
from models.driver import Driver, DriverCreate, DriverLogin, DriverResponse
from auth.jwt_handler import create_access_token, verify_token
from auth.password_handler import hash_password, verify_password


# --- Pydantic Model for Portfolio ---
class DriverPortfolio(BaseModel):
    # Add full_name, making it optional
    full_name: Optional[str] = None
    age: int
    car_model: str
    car_year: int
    car_color: str
    experience_years: int
    bio: str
    languages: List[str] = []
    certifications: List[str] = []
    profile_image: Optional[str] = None  # For Base64 image data

    @validator('languages', 'certifications', pre=True)
    def split_string_to_list(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(',') if item.strip()]
        if isinstance(v, list):
            return v
        return []

    class Config:
        orm_mode = True


# NEW: A response model that combines Driver and their optional Portfolio
class DriverPublicProfile(DriverResponse):
    portfolio: Optional[DriverPortfolio] = None
    
    
# --- Router Setup ---
router = APIRouter(prefix="/api/drivers", tags=["drivers"])

# --- Dependency to get current driver ---
async def get_current_driver(request: Request):
    """Dependency to verify token and fetch the current authenticated driver."""
    from fastapi.security import HTTPBearer
    security = HTTPBearer()
    credentials = request.headers.get("authorization")
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication credentials were not provided.")
    
    token = credentials.split(" ")[-1]
    payload = verify_token(token)
    if not payload or payload.get("user_type") != "driver":
        raise HTTPException(status_code=403, detail="Invalid token or not a driver account.")
    
    driver_id = payload.get("sub")
    driver = await request.app.mongodb["drivers"].find_one({"_id": ObjectId(driver_id)})
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found.")
    
    driver["id"] = str(driver["_id"])
    return Driver(**driver)


# --- UPDATED Driver Portfolio Endpoints ---

@router.get("/portfolio", response_model=DriverPortfolio)
async def get_my_portfolio(request: Request, current_driver: Driver = Depends(get_current_driver)):
    """
    Fetches the portfolio for the authenticated driver.
    If no portfolio exists, it creates and returns a default one based on registration data.
    """
    portfolio_data = await request.app.mongodb["driver_portfolios"].find_one({"driver_id": current_driver.id})
    
    if portfolio_data:
        # If portfolio exists, return it
        return portfolio_data
    else:
        # If no portfolio exists, create a default object and return it (status 200)
        # This prevents the 404 error on the frontend.
        default_portfolio = {
            "full_name": current_driver.full_name,
            "car_model": current_driver.car_type,
            "car_year": datetime.now().year, # Sensible default
            "car_color": "Not specified",
            "age": 18, # Sensible default
            "experience_years": 0,
            "bio": "",
            "languages": [],
            "certifications": [],
            "profile_image": None
        }
        return default_portfolio


# --- Helper function to update a driver's average rating ---
async def update_driver_average_rating(db, driver_id: str):
    """Calculates and updates a driver's average rating and total trips based on their ratings."""
    pipeline = [
        {"$match": {"driver_id": driver_id}},
        {"$group": {
            "_id": "$driver_id",
            "averageRating": {"$avg": "$rating"},
            "totalRatings": {"$sum": 1}
        }}
    ]
    rating_stats = await db["ratings"].aggregate(pipeline).to_list(length=1)

    if rating_stats:
        stats = rating_stats[0]
        # Round the average rating to the nearest 0.5
        rounded_rating = round(stats["averageRating"] * 2) / 2
        
        await db["drivers"].update_one(
            {"_id": ObjectId(driver_id)},
            {"$set": {
                "rating": rounded_rating,
                "total_trips": stats["totalRatings"] # Using total ratings as the trip count
            }}
        )


@router.put("/portfolio", response_model=DriverPortfolio)
async def update_or_create_driver_portfolio(portfolio_update: DriverPortfolio, request: Request, current_driver: Driver = Depends(get_current_driver)):
    """
    Creates or updates the portfolio for the currently authenticated driver.
    The 'full_name' from the payload is now saved.
    """
    portfolio_doc = portfolio_update.dict()
    portfolio_doc["driver_id"] = current_driver.id
    portfolio_doc["updated_at"] = datetime.utcnow()
    
    # Use upsert=True to create the document if it doesn't exist, or update it if it does.
    await request.app.mongodb["driver_portfolios"].update_one(
        {"driver_id": current_driver.id},
        {"$set": portfolio_doc},
        upsert=True
    )
    
    # Mark the main driver profile as having a completed portfolio
    await request.app.mongodb["drivers"].update_one(
        {"_id": ObjectId(current_driver.id)},
        {"$set": {"portfolio_completed": True}}
    )
    
    return portfolio_doc

# --- Core Driver Endpoints ---

@router.post("/register", response_model=DriverResponse)
async def register_driver(driver: DriverCreate, request: Request):
    if await request.app.mongodb["drivers"].find_one({"email": driver.email}):
        raise HTTPException(status_code=400, detail="Email already registered.")
    
    driver_doc = driver.dict()
    driver_doc["password"] = hash_password(driver.password)
    driver_doc.update({
        "created_at": datetime.utcnow(),
        "rating": 0.0,
        "total_trips": 0,
        "portfolio_completed": False
    })
    
    result = await request.app.mongodb["drivers"].insert_one(driver_doc)
    new_driver = await request.app.mongodb["drivers"].find_one({"_id": result.inserted_id})
    return new_driver

@router.post("/login")
async def login_driver(driver_credentials: DriverLogin, request: Request):
    driver = await request.app.mongodb["drivers"].find_one({"email": driver_credentials.email})
    if not driver or not verify_password(driver_credentials.password, driver["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    access_token = create_access_token(data={"sub": str(driver["_id"])}, user_type="driver")
    driver["id"] = str(driver["_id"])
    return {"access_token": access_token, "token_type": "bearer", "driver": DriverResponse(**driver)}
    
@router.get("/me", response_model=DriverResponse)
async def get_current_driver_info(current_driver: Driver = Depends(get_current_driver)):
    """Returns the basic information of the currently authenticated driver."""
    return current_driver



@router.post("/availability")
async def create_driver_availability(availability: dict, request: Request, current_driver: Driver = Depends(get_current_driver)):
    availability_doc = {
        "driver_id": current_driver.id,
        "working_hours": availability.get("working_hours"),
        "locations": availability.get("locations"),
        "car_types": availability.get("car_types"),
        "created_at": datetime.utcnow()
    }
    await request.app.mongodb["driver_availability"].update_one(
        {"driver_id": current_driver.id},
        {"$set": availability_doc},
        upsert=True
    )
    return {"message": "Availability updated successfully"}

@router.get("/availability")
async def get_driver_availability(request: Request, location: Optional[str] = None, car_type: Optional[str] = None, date: Optional[str] = None):
    filter_query = {}
    if location:
        filter_query["locations"] = {"$regex": location, "$options": "i"}
    if car_type:
        filter_query["car_types"] = car_type
    cursor = request.app.mongodb["driver_availability"].find(filter_query)
    availability_list = await cursor.to_list(length=100)
    return availability_list

@router.get("/", response_model=List[DriverPublicProfile])
async def get_all_drivers_with_portfolios(request: Request):
    """
    Gets all drivers and joins their portfolio information using an aggregation pipeline.
    """
    pipeline = [
        {
            # Stage 1: Convert the driver's _id (ObjectId) to a string for matching
            "$addFields": {
                "driver_id_str": {"$toString": "$_id"}
            }
        },
        {
            # Stage 2: Perform a left join with the driver_portfolios collection
            "$lookup": {
                "from": "driver_portfolios",
                "localField": "driver_id_str",
                "foreignField": "driver_id",
                "as": "portfolio_docs"
            }
        },
        {
            # Stage 3: Deconstruct the portfolio_docs array.
            # preserveNullAndEmptyArrays ensures drivers without portfolios are still included.
            "$unwind": {
                "path": "$portfolio_docs",
                "preserveNullAndEmptyArrays": True
            }
        },
        {
            # Stage 4: Create the final structure
            "$project": {
                # Include all original driver fields
                "_id": 1, "id": "$driver_id_str", "full_name": 1, "email": 1, "phone": 1,
                "car_type": 1, "license_number": 1, "working_area": 1, "rating": 1,
                "total_trips": 1, "portfolio_completed": 1, "created_at": 1,
                # Embed the portfolio document if it exists
                "portfolio": "$portfolio_docs"
            }
        }
    ]

    drivers_cursor = request.app.mongodb["drivers"].aggregate(pipeline)
    drivers_list = await drivers_cursor.to_list(length=100)
    
    # Clean up the portfolio field: set to None if it's an empty document
    for driver in drivers_list:
        if driver.get("portfolio") and not driver["portfolio"].get("driver_id"):
            driver["portfolio"] = None
            
    return drivers_list

# --- Pydantic Models for this Router ---

class DriverStats(BaseModel):
    totalTrips: int
    totalEarnings: float
    averageRating: float
    thisMonth: int

class ActivityItem(BaseModel):
    id: str
    type: str  # 'pickup' or 'tour_created'
    title: str
    date: datetime
    status: str
    details: Optional[str] = None

# --- Endpoints ---

@router.get("/stats", response_model=DriverStats)
async def get_driver_stats(request: Request, driver = Depends(get_current_driver)): # Removed incorrect type hint
    """Calculates and returns key statistics for the current driver."""
    db = request.app.mongodb
    # ✅ FIX: Use dot notation to access object attributes
    driver_id = driver.id

    # Get all tour IDs for this driver
    tours = await db["tours"].find({"driver_id": driver_id}).to_list(length=None)
    tour_ids = [str(t["_id"]) for t in tours]

    # Calculate Total Trips and Earnings from bookings on this driver's tours
    total_trips = 0
    total_earnings = 0
    if tour_ids:
        booking_stats_pipeline = [
            {"$match": {"tour_id": {"$in": tour_ids}, "status": {"$ne": "cancelled"}}},
            {"$group": {
                "_id": None,
                "totalEarnings": {"$sum": "$total_price"},
                "totalTrips": {"$sum": "$number_of_people"}
            }}
        ]
        booking_stats = await db["bookings"].aggregate(booking_stats_pipeline).to_list(length=1)
        if booking_stats:
            total_trips = booking_stats[0].get("totalTrips", 0)
            total_earnings = booking_stats[0].get("totalEarnings", 0)

    # Calculate tours created this month
    today = date.today()
    start_of_month = datetime(today.year, today.month, 1)
    this_month_tours = await db["tours"].count_documents({
        "driver_id": driver_id,
        "created_at": {"$gte": start_of_month}
    })

    return {
        "totalTrips": total_trips,
        "totalEarnings": round(total_earnings, 2),
        # ✅ FIX: Use dot notation here as well
        "averageRating": driver.rating if hasattr(driver, 'rating') else 0.0,
        "thisMonth": this_month_tours
    }


@router.get("/recent-activity", response_model=List[ActivityItem])
async def get_driver_recent_activity(request: Request, driver = Depends(get_current_driver)): # Removed incorrect type hint
    """
    Fetches a combined list of a driver's recent activity.
    For now, it only includes newly created tours.
    """
    db = request.app.mongodb
    # ✅ FIX: Use dot notation to access object attributes
    driver_id = driver.id
    
    activity_list = []
    
    # Fetch recent tours created by the driver
    tours_cursor = db["tours"].find(
        {"driver_id": driver_id}
    ).sort("created_at", -1).limit(5)
    
    tours_list = await tours_cursor.to_list(length=5)

    for tour in tours_list:
        activity_list.append({
            "id": str(tour["_id"]),
            "type": "tour_created",
            "title": f"New Tour: {tour['from_location']} → {tour['to_location']}",
            "date": tour["created_at"],
            "status": tour.get("status", "Active"),
            "details": f"${tour.get('price_per_person', 0)} per person"
        })

    activity_list.sort(key=lambda x: x["date"], reverse=True)
    
    return activity_list[:5]

# --- New Pydantic Models for Ratings ---
class RatingCreate(BaseModel):
    booking_id: str
    rating: int = Field(..., gt=0, le=5) # Rating must be between 1 and 5



# --- NEW Endpoint to Add a Rating ---
@router.post("/{driver_id}/rate", status_code=201)
async def rate_driver(
    driver_id: str, 
    rating_data: RatingCreate, 
    request: Request, 
    current_user: dict = Depends(get_current_user)
):
    """Allows a user to rate a driver for a completed booking."""
    db = request.app.mongodb
    
    # 1. Validate the booking
    booking = await db["bookings"].find_one({"_id": ObjectId(rating_data.booking_id)})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    
    # 2. Check if the booking belongs to the current user
    if booking.get("user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="You can only rate your own bookings.")
        
    # 3. Check if the booking's driver matches the driver_id in the URL
    tour = await db["tours"].find_one({"_id": ObjectId(booking["tour_id"])})
    if not tour or tour.get("driver_id") != driver_id:
        raise HTTPException(status_code=400, detail="Driver does not match the booking.")
        
    # 4. Check if the booking is completed
    if booking.get("status") != "completed":
        raise HTTPException(status_code=400, detail="You can only rate completed rides.")

    # 5. Check if this booking has already been rated
    existing_rating = await db["ratings"].find_one({"booking_id": rating_data.booking_id})
    if existing_rating:
        raise HTTPException(status_code=400, detail="This booking has already been rated.")

    # 6. Create and save the new rating
    new_rating = {
        "driver_id": driver_id,
        "user_id": current_user["id"],
        "booking_id": rating_data.booking_id,
        "rating": rating_data.rating,
        "created_at": datetime.utcnow()
    }
    await db["ratings"].insert_one(new_rating)
    
    # 7. Update the driver's average rating
    await update_driver_average_rating(db, driver_id)
    
    return {"message": "Rating submitted successfully."}
