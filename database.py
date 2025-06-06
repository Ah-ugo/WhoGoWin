from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import IndexModel
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# MongoDB connection
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "nigerian_lottery")

client = AsyncIOMotorClient(MONGODB_URL)
database = client[DATABASE_NAME]

# Collections
users_collection = database.users
draws_collection = database.draws
tickets_collection = database.tickets
transactions_collection = database.transactions
platform_wallet_collection = database.platform_wallet
notifications_collection = database.notifications


async def init_db():
    """Initialize database with indexes and default data"""

    # Create indexes for users
    await users_collection.create_indexes([
        IndexModel("email", unique=True),
        IndexModel("referral_code", unique=True),
    ])

    # Create indexes for draws
    await draws_collection.create_indexes([
        IndexModel("status"),
        IndexModel("draw_type"),
        IndexModel("end_time"),
    ])

    # Create indexes for tickets
    await tickets_collection.create_indexes([
        IndexModel("user_id"),
        IndexModel("draw_id"),
        IndexModel([("user_id", 1), ("draw_id", 1)]),
    ])

    # Create indexes for transactions
    await transactions_collection.create_indexes([
        IndexModel("user_id"),
        IndexModel("date"),
        IndexModel([("user_id", 1), ("date", -1)]),
    ])

    # Initialize platform wallet if it doesn't exist
    platform_wallet = await platform_wallet_collection.find_one({"_id": "platform"})
    if not platform_wallet:
        await platform_wallet_collection.insert_one({
            "_id": "platform",
            "total_earnings": 0,
            "total_payouts": 0,
            "current_balance": 0,
            "created_at": datetime.utcnow()
        })

    print("Database initialized successfully")


async def get_database():
    return database
