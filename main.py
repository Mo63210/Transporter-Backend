# main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

# Import routers
from drivers.drivers import router as drivers_router
from users.users import router as users_router
from tours.tours import router as tours_router
from bookings.bookings import router as bookings_router
from notifications.notifications import router as notifications_router 
from ratings.ratings import router as ratings_router
from pickup.pickup import router as pickup_router
from search.search import router as search_router
from discounts.discounts import router as discounts_router 
load_dotenv()

app = FastAPI(title="Pickup App API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://transporter-frontend.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_db_client():
    app.mongodb_client = AsyncIOMotorClient(os.getenv("MONGODB_URL", "mongodb+srv://grad_project_632:workout123456789@cluster0.wo9llcy.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"))
    app.mongodb = app.mongodb_client["pickup-app"]

@app.on_event("shutdown")
async def shutdown_db_client():
    app.mongodb_client.close()

# Include all routers
app.include_router(users_router)
app.include_router(drivers_router)
app.include_router(tours_router)
app.include_router(bookings_router)
app.include_router(notifications_router) 
app.include_router(ratings_router)
app.include_router(pickup_router)
app.include_router(search_router)
app.include_router(discounts_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)