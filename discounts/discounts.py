# src/routes/discounts.py

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

router = APIRouter(prefix="/api/discounts", tags=["discounts"])

class Discount(BaseModel):
    id: str
    code: str
    amount: float
    is_percent: bool
    description: str

@router.get("/active", response_model=List[Discount])
async def get_active_discounts(request: Request):
    """Fetches all active and valid discounts to be shown as notifications."""
    now = datetime.utcnow()
    query = {
        "is_active": True,
        "start_date": {"$lte": now},
        "end_date": {"$gte": now}
    }
    discounts_cursor = request.app.mongodb["discounts"].find(query)
    discounts = await discounts_cursor.to_list(length=100)

    for discount in discounts:
        discount["id"] = str(discount["_id"])
        
    return discounts

@router.get("/validate/{code}", response_model=Discount)
async def validate_discount_code(code: str, request: Request):
    """Validates a discount code and returns its details if valid."""
    now = datetime.utcnow()
    query = {
        "code": code.upper(), # Store and check codes in uppercase
        "is_active": True,
        "start_date": {"$lte": now},
        "end_date": {"$gte": now}
    }
    discount = await request.app.mongodb["discounts"].find_one(query)

    if not discount:
        raise HTTPException(status_code=404, detail="Invalid or expired discount code.")
    
    discount["id"] = str(discount["_id"])
    return discount