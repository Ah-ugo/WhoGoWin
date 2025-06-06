from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
from datetime import datetime, timedelta
import asyncio
import os
from dotenv import load_dotenv

from routes import auth, users, draws, tickets, wallet, notifications
from database import init_db
from services.draw_service import DrawService
from services.notification_service import NotificationService

load_dotenv()

# Initialize services
draw_service = DrawService()
notification_service = NotificationService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()

    # Start background tasks
    asyncio.create_task(draw_service.start_draw_scheduler())
    asyncio.create_task(notification_service.start_notification_scheduler())

    yield

    # Shutdown
    pass


app = FastAPI(
    title="WhoGoWin Lottery API",
    description="WhoGoWin Lottery API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(draws.router, prefix="/api/v1/draws", tags=["Draws"])
app.include_router(tickets.router, prefix="/api/v1/tickets", tags=["Tickets"])
app.include_router(wallet.router, prefix="/api/v1/wallet", tags=["Wallet"])
app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["Notifications"])


@app.get("/")
async def root():
    return {"message": "Nigerian Lottery API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow()}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
