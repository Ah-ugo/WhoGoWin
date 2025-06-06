from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from datetime import datetime
from typing import List
from bson import ObjectId

from routes.auth import get_current_user, get_current_admin_user
from database import notifications_collection, users_collection
from services.notification_service import NotificationService
from models.user import Role

router = APIRouter()
notification_service = NotificationService()

class PushTokenRequest(BaseModel):
    token: str

class BulkNotificationRequest(BaseModel):
    title: str
    body: str
    notification_type: str = "general"

class NotificationUpdateRequest(BaseModel):
    notification_ids: List[str]
    read: bool

@router.post("/register-token")
async def register_push_token(
        token_data: PushTokenRequest,
        current_user: dict = Depends(get_current_user)
):
    """Register user's push notification token"""
    await users_collection.update_one(
        {"_id": current_user["_id"]},
        {
            "$set": {
                "push_token": token_data.token,
                "push_token_updated": datetime.utcnow()
            }
        }
    )
    return {"message": "Push token registered successfully"}

@router.post("/send-test")
async def send_test_notification(current_user: dict = Depends(get_current_user)):
    """Send a test notification to current user"""
    push_token = current_user.get("push_token")
    if not push_token:
        raise HTTPException(status_code=400, detail="No push token registered")

    await notification_service.send_push_notification(
        push_token,
        "Test Notification",
        "This is a test notification from Nigerian Lottery!"
    )
    return {"message": "Test notification sent"}

@router.get("/history")
async def get_notification_history(current_user: dict = Depends(get_current_user)):
    """Get user's notification history"""
    notifications = await notifications_collection.find(
        {"user_id": str(current_user["_id"])}
    ).sort("created_at", -1).limit(50).to_list(50)

    result = []
    for notif in notifications:
        result.append({
            "id": str(notif["_id"]),
            "title": notif["title"],
            "body": notif["body"],
            "type": notif.get("type", "general"),
            "read": notif.get("read", False),
            "created_at": notif["created_at"]
        })
    return result

@router.post("/send-bulk", response_model=dict)
async def send_bulk_notification(
        notification_data: BulkNotificationRequest,
        current_user: dict = Depends(get_current_admin_user)
):
    """Send a notification to all users with push tokens (Admin only)"""
    try:
        await notification_service.send_admin_bulk_notification(
            notification_data.title,
            notification_data.body,
            notification_data.notification_type
        )
        return {"message": "Bulk notification sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/history/{user_id}", response_model=List[dict])
async def get_user_notification_history(
        user_id: str,
        current_user: dict = Depends(get_current_admin_user)
):
    """Get notification history for a specific user (Admin only)"""
    try:
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        notifications = await notifications_collection.find(
            {"user_id": user_id}
        ).sort("created_at", -1).limit(50).to_list(50)

        result = []
        for notif in notifications:
            result.append({
                "id": str(notif["_id"]),
                "title": notif["title"],
                "body": notif["body"],
                "type": notif.get("type", "general"),
                "read": notif.get("read", False),
                "created_at": notif["created_at"]
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid user ID")

@router.put("/update", response_model=dict)
async def update_notification_status(
        update_data: NotificationUpdateRequest,
        current_user: dict = Depends(get_current_admin_user)
):
    """Mark notifications as read/unread for a user (Admin only)"""
    try:
        notification_ids = [ObjectId(nid) for nid in update_data.notification_ids]
        await notifications_collection.update_many(
            {"_id": {"$in": notification_ids}},
            {"$set": {"read": update_data.read}}
        )
        return {"message": f"Notifications marked as {'read' if update_data.read else 'unread'}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid notification IDs")


@router.put("/mark-read")
async def mark_notifications_read(
    update_data: NotificationUpdateRequest,
    current_user: dict = Depends(get_current_user)
):
    notification_ids = [ObjectId(nid) for nid in update_data.notification_ids]
    await notifications_collection.update_many(
        {"_id": {"$in": notification_ids}, "user_id": str(current_user["_id"])},
        {"$set": {"read": update_data.read}}
    )
    return {"message": f"Notifications marked as {'read' if update_data.read else 'unread'}"}