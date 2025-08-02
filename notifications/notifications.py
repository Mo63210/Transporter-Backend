# notifications/notifications.py

from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List
from auth.jwt_handler import verify_token # Assuming you have a generic token verifier

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

# --- Dependency to get current user ID from token ---
async def get_current_user_id(request: Request):
    credentials = request.headers.get("authorization")
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing credentials")
    
    token = credentials.split(" ")[-1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Return both user ID and type for more flexible use
    return {"user_id": payload.get("sub"), "user_type": payload.get("user_type")}

# --- Notification Endpoints ---

@router.get("/")
async def get_my_notifications(request: Request, user_info: dict = Depends(get_current_user_id)):
    """Fetches notifications for the currently authenticated user or driver."""
    
    # You can customize the query based on user type if needed
    user_id = user_info["user_id"]
    
    # Example query: find notifications where the recipient_id matches the current user's ID
    notifications_cursor = request.app.mongodb["notifications"].find(
        {"recipient_id": user_id},
        sort=[("created_at", -1)] # Show newest first
    ).limit(20) # Limit the number of notifications returned

    notifications = await notifications_cursor.to_list(length=20)

    # Convert ObjectId to string for JSON serialization
    for notif in notifications:
        notif["_id"] = str(notif["_id"])

    return notifications

@router.post("/{notification_id}/mark-as-read")
async def mark_notification_as_read(notification_id: str, request: Request, user_info: dict = Depends(get_current_user_id)):
    """Marks a specific notification as read."""
    from bson import ObjectId

    result = await request.app.mongodb["notifications"].update_one(
        {
            "_id": ObjectId(notification_id),
            "recipient_id": user_info["user_id"] # Ensure user can only update their own notifications
        },
        {"$set": {"is_read": True}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found or you don't have permission to update it.")

    return {"message": "Notification marked as read."}