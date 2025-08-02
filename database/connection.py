from motor.motor_asyncio import AsyncIOMotorClient
import os

async def get_database():
    client = AsyncIOMotorClient(os.getenv("MONGODB_URL", "mongodb://localhost:27017"))
    return client["pickup-app"] 