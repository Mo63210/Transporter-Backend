# pickup.py

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from typing import List, Optional
from auth.jwt_handler import verify_token

# --- Pydantic Models ---
# ... (Models are unchanged) ...
class PickupRequestCreate(BaseModel):
    pickup_location: str
    destination: str
    pickup_time: datetime
    number_of_people: int
    preferred_car_type: Optional[str] = None
    allow_other_passengers: bool = False
    special_requests: Optional[str] = ""

class PickupRequest(BaseModel):
    id: str = Field(alias="_id")
    user_id: str
    status: str
    driver_id: Optional[str] = None
    pickup_location: str
    destination: str
    pickup_time: datetime
    number_of_people: int
    preferred_car_type: Optional[str] = None
    allow_other_passengers: bool
    special_requests: Optional[str] = ""
    created_at: datetime
    class Config:
        allow_population_by_field_name = True

class UserInfoForPickup(BaseModel):
    id: str = Field(alias="_id")
    full_name: str
    phone: str
    class Config:
        allow_population_by_field_name = True

class EnrichedPickupRequest(PickupRequest):
    user: Optional[UserInfoForPickup] = None

class PickupStatusUpdateResponse(BaseModel):
    id: str = Field(alias="_id")
    status: str
    driver_id: Optional[str] = None
    class Config:
        allow_population_by_field_name = True

router = APIRouter(prefix="/api/pickup", tags=["pickup_requests"])

# --- Dependencies ---
# ... (get_current_user, get_current_driver are unchanged) ...
async def get_current_user(request: Request):
    from fastapi.security import HTTPBearer
    credentials = await HTTPBearer()(request)
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication credentials were not provided.")
    payload = verify_token(credentials.credentials)
    if not payload or payload.get("user_type") != "user":
        raise HTTPException(status_code=403, detail="Access forbidden: User role required.")
    user_id = payload.get("sub")
    user = await request.app.mongodb["users"].find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user["id"] = str(user["_id"])
    return user

async def get_current_driver(request: Request):
    from fastapi.security import HTTPBearer
    credentials = await HTTPBearer()(request)
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication credentials were not provided.")
    payload = verify_token(credentials.credentials)
    if not payload or payload.get("user_type") != "driver":
        raise HTTPException(status_code=403, detail="Access forbidden: Driver role required.")
    driver_id = payload.get("sub")
    driver = await request.app.mongodb["drivers"].find_one({"_id": ObjectId(driver_id)})
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found.")
    driver["id"] = str(driver["_id"])
    return driver
    
# --- API Endpoints for Users ---
# ... (User endpoints are unchanged) ...
@router.post("/request", response_model=PickupRequest)
async def create_pickup_request(request_data: PickupRequestCreate, request: Request, current_user: dict = Depends(get_current_user)):
    request_doc = request_data.dict()
    request_doc["user_id"] = current_user["id"]
    request_doc["status"] = "pending"
    request_doc["created_at"] = datetime.utcnow()
    request_doc["driver_id"] = None
    result = await request.app.mongodb["pickup_requests"].insert_one(request_doc)
    new_request_doc = await request.app.mongodb["pickup_requests"].find_one({"_id": result.inserted_id})
    if not new_request_doc:
        raise HTTPException(status_code=404, detail="Could not create or find pickup request.")
    new_request_doc["_id"] = str(new_request_doc["_id"])
    return new_request_doc

@router.get("/my-requests", response_model=List[PickupRequest])
async def get_my_pickup_requests(request: Request, current_user: dict = Depends(get_current_user)):
    requests_cursor = request.app.mongodb["pickup_requests"].find(
        {"user_id": current_user["id"]},
    ).sort("created_at", -1)
    results = await requests_cursor.to_list(length=None)
    for req in results:
        req["_id"] = str(req["_id"])
    return results

@router.patch("/my-requests/{request_id}/cancel", response_model=PickupStatusUpdateResponse)
async def user_cancel_request(request_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(request_id):
        raise HTTPException(status_code=400, detail="Invalid request ID.")
    request_doc = await request.app.mongodb["pickup_requests"].find_one({"_id": ObjectId(request_id)})
    if not request_doc:
        raise HTTPException(status_code=404, detail="Request not found.")
    if request_doc["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="You are not authorized to cancel this request.")
    if request_doc["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot cancel a request with status '{request_doc['status']}'.")
    result = await request.app.mongodb["pickup_requests"].find_one_and_update(
        {"_id": ObjectId(request_id)},
        {"$set": {"status": "cancelled"}},
        return_document=True
    )
    if result:
        result["_id"] = str(result["_id"])
    return result

# --- Endpoints for Drivers ---
def process_request_results(results: list) -> list:
    for req in results:
        req["_id"] = str(req["_id"])
        user_data = req.get("user")
        if user_data and user_data.get("_id"):
            user_data["_id"] = str(user_data["_id"])
        else:
            req["user"] = None
    return results

@router.get("/requests", response_model=List[EnrichedPickupRequest])
async def get_pending_pickup_requests(request: Request, driver: dict = Depends(get_current_driver)):
    pipeline = [ {"$match": {"status": "pending"}}, {"$sort": {"created_at": -1}}, {"$addFields": {"user_object_id": {"$toObjectId": "$user_id"}}}, {"$lookup": {"from": "users", "localField": "user_object_id", "foreignField": "_id", "as": "user_info"}}, {"$unwind": {"path": "$user_info", "preserveNullAndEmptyArrays": True}}, {"$project": { "_id": 1, "pickup_location": 1, "destination": 1, "pickup_time": 1, "number_of_people": 1, "preferred_car_type": 1, "allow_other_passengers": 1, "special_requests": 1, "status": 1, "created_at": 1, "user_id": 1, "driver_id": 1, "user": {"_id": "$user_info._id", "full_name": "$user_info.full_name", "phone": "$user_info.phone"} }} ]
    requests_cursor = request.app.mongodb["pickup_requests"].aggregate(pipeline)
    results = await requests_cursor.to_list(length=None)
    return process_request_results(results)

@router.get("/", response_model=List[EnrichedPickupRequest])
async def get_all_pickup_requests(request: Request, driver: dict = Depends(get_current_driver)):
    pipeline = [ {"$sort": {"created_at": -1}}, {"$addFields": {"user_object_id": {"$toObjectId": "$user_id"}}}, {"$lookup": {"from": "users", "localField": "user_object_id", "foreignField": "_id", "as": "user_info"}}, {"$unwind": {"path": "$user_info", "preserveNullAndEmptyArrays": True}}, {"$project": { "_id": 1, "pickup_location": 1, "destination": 1, "pickup_time": 1, "number_of_people": 1, "preferred_car_type": 1, "allow_other_passengers": 1, "special_requests": 1, "status": 1, "created_at": 1, "user_id": 1, "driver_id": 1, "user": {"_id": "$user_info._id", "full_name": "$user_info.full_name", "phone": "$user_info.phone"} }} ]
    requests_cursor = request.app.mongodb["pickup_requests"].aggregate(pipeline)
    results = await requests_cursor.to_list(length=None)
    return process_request_results(results)

@router.patch("/request/{request_id}/accept", response_model=PickupStatusUpdateResponse)
async def accept_pickup_request(request_id: str, request: Request, driver: dict = Depends(get_current_driver)):
    if not ObjectId.is_valid(request_id):
        raise HTTPException(status_code=400, detail="Invalid request ID.")
    result = await request.app.mongodb["pickup_requests"].find_one_and_update(
        {"_id": ObjectId(request_id), "status": "pending"},
        {"$set": {"status": "accepted", "driver_id": driver["id"]}},
        return_document=True )
    if not result:
        raise HTTPException(status_code=404, detail="Request not found or already handled.")
    result["_id"] = str(result["_id"])
    return result

@router.patch("/request/{request_id}/cancel", response_model=PickupStatusUpdateResponse)
async def cancel_pickup_request(request_id: str, request: Request, driver: dict = Depends(get_current_driver)):
    if not ObjectId.is_valid(request_id):
        raise HTTPException(status_code=400, detail="Invalid request ID.")
    query = { "_id": ObjectId(request_id), "$or": [ {"status": "pending"}, {"status": "accepted", "driver_id": driver["id"]} ] }
    result = await request.app.mongodb["pickup_requests"].find_one_and_update(
        query,
        {"$set": {"status": "pending", "driver_id": None}},
        return_document=True )
    if not result:
        raise HTTPException(status_code=404, detail="Request not found or you are not authorized to cancel it.")
    result["_id"] = str(result["_id"])
    return result

@router.patch("/request/{request_id}/complete", response_model=PickupStatusUpdateResponse)
async def complete_pickup_request(request_id: str, request: Request, driver: dict = Depends(get_current_driver)):
    """Allows a driver to mark an accepted request as complete."""
    if not ObjectId.is_valid(request_id):
        raise HTTPException(status_code=400, detail="Invalid request ID.")

    # Atomically find and update the request only if it's 'accepted' and belongs to this driver
    result = await request.app.mongodb["pickup_requests"].find_one_and_update(
        {"_id": ObjectId(request_id), "status": "accepted", "driver_id": driver["id"]},
        {"$set": {"status": "completed"}},
        return_document=True
    )

    if not result:
        raise HTTPException(status_code=404, detail="Request not found, not assigned to you, or not in 'accepted' state.")

    result["_id"] = str(result["_id"])
    return result