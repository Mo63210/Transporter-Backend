from fastapi import APIRouter, HTTPException, Request, Depends, status
from models.user import User, UserCreate, UserLogin, UserResponse
from auth.jwt_handler import create_access_token, verify_token
from auth.password_handler import hash_password, verify_password
from bson import ObjectId
from datetime import datetime
from typing import List

router = APIRouter(prefix="/api/users", tags=["users"])

# Dependency to get current user from JWT
async def get_current_user(request: Request):
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    security = HTTPBearer()
    credentials = await security(request)
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing credentials")
    payload = verify_token(credentials.credentials)
    if not payload or payload.get("user_type") != "user":
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = payload.get("sub")
    user = await request.app.mongodb["users"].find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    user["id"] = str(user["_id"])
    return User(**user)

@router.post("/register", response_model=UserResponse)
async def register_user(user: UserCreate, request: Request):
    existing_user = await request.app.mongodb["users"].find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = hash_password(user.password)
    user_doc = {
        "email": user.email,
        "password": hashed_password,
        "full_name": user.full_name,
        "phone": user.phone,
        "created_at": datetime.utcnow(),
        "rating": 0,
        "total_rides": 0
    }
    result = await request.app.mongodb["users"].insert_one(user_doc)
    user_doc["_id"] = result.inserted_id
    user_doc["id"] = str(result.inserted_id)
    return UserResponse(**user_doc)

@router.post("/login")
async def login_user(user_credentials: UserLogin, request: Request):
    user = await request.app.mongodb["users"].find_one({"email": user_credentials.email})
    if not user or not verify_password(user_credentials.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token = create_access_token(data={"sub": str(user["_id"]),}, user_type="user")
    user["id"] = str(user["_id"])
    return {"access_token": access_token, "token_type": "bearer", "user": UserResponse(**user)}

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(request: Request, current_user: User = Depends(get_current_user)):
    return current_user

@router.get("/stats")
async def get_user_stats(request: Request, current_user: User = Depends(get_current_user)):
    pipeline = [
        {"$match": {"user_id": current_user.id}},
        {"$group": {
            "_id": None,
            "totalRides": {"$sum": 1},
            "totalSpent": {"$sum": "$total_price"},
            "thisMonth": {
                "$sum": {
                    "$cond": [
                        {"$gte": ["$created_at", datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)]},
                        1,
                        0
                    ]
                }
            }
        }}
    ]
    stats_result = await request.app.mongodb["bookings"].aggregate(pipeline).to_list(length=1)
    if stats_result:
        stats = stats_result[0]
        return {
            "totalRides": stats.get("totalRides", 0),
            "totalSpent": stats.get("totalSpent", 0),
            "averageRating": current_user.rating,
            "thisMonth": stats.get("thisMonth", 0)
        }
    else:
        return {
            "totalRides": 0,
            "totalSpent": 0,
            "averageRating": current_user.rating,
            "thisMonth": 0
        } 