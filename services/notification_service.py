import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict
from bson import ObjectId

from database import users_collection, notifications_collection, draws_collection

class NotificationService:
    def __init__(self):
        self.expo_push_url = "https://exp.host/--/api/v2/push/send"

    async def start_notification_scheduler(self):
        """Start background task for scheduled notifications"""
        while True:
            try:
                await self.send_draw_reminders()
                await asyncio.sleep(300)  # Check every 5 minutes
            except Exception as e:
                print(f"Error in notification scheduler: {e}")
                await asyncio.sleep(300)

    async def send_push_notification(self, push_token: str, title: str, body: str, data: Dict = None):
        """Send push notification via Expo"""
        if not push_token:
            return

        message = {
            "to": push_token,
            "title": title,
            "body": body,
            "sound": "default",
            "priority": "high"
        }

        if data:
            message["data"] = data

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                        self.expo_push_url,
                        json=message,
                        headers={"Content-Type": "application/json"}
                ) as response:
                    result = await response.json()
                    print(f"Push notification sent: {result}")
        except Exception as e:
            print(f"Error sending push notification: {e}")

    async def send_bulk_notifications(self, messages: List[Dict]):
        """Send multiple push notifications"""
        if not messages:
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                        self.expo_push_url,
                        json=messages,
                        headers={"Content-Type": "application/json"}
                ) as response:
                    result = await response.json()
                    print(f"Bulk notifications sent: {result}")
        except Exception as e:
            print(f"Error sending bulk notifications: {e}")

    async def send_admin_bulk_notification(self, title: str, body: str, notification_type: str = "general"):
        """Send a notification to all users with push tokens and save to database"""
        users_with_tokens = await users_collection.find({
            "push_token": {"$exists": True, "$ne": None}
        }).to_list(1000)

        messages = []
        for user in users_with_tokens:
            messages.append({
                "to": user["push_token"],
                "title": title,
                "body": body,
                "sound": "default",
                "priority": "high",
                "data": {"type": notification_type}
            })
            # Save notification to database
            await self.save_notification(
                user_id=str(user["_id"]),
                title=title,
                body=body,
                notification_type=notification_type
            )

        if messages:
            await self.send_bulk_notifications(messages)

    async def send_draw_reminders(self):
        """Send reminders for draws ending soon"""
        current_time = datetime.utcnow()

        upcoming_draws = await draws_collection.find({
            "status": "active",
            "end_time": {
                "$gte": current_time,
                "$lte": current_time + timedelta(hours=1)
            },
            "reminder_sent": {"$ne": True}
        }).to_list(10)

        for draw in upcoming_draws:
            users_with_tokens = await users_collection.find({
                "push_token": {"$exists": True, "$ne": None}
            }).to_list(1000)

            messages = []
            for user in users_with_tokens:
                time_remaining = draw["end_time"] - current_time
                hours = int(time_remaining.total_seconds() // 3600)
                minutes = int((time_remaining.total_seconds() % 3600) // 60)

                time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

                messages.append({
                    "to": user["push_token"],
                    "title": f"⏰ {draw['draw_type']} Draw Ending Soon!",
                    "body": f"Only {time_str} left to buy your ticket. Current pot: ₦{draw.get('total_pot', 0):,.0f}",
                    "sound": "default",
                    "data": {"draw_id": str(draw["_id"]), "type": "draw_reminder"}
                })
                await self.save_notification(
                    user_id=str(user["_id"]),
                    title=f"⏰ {draw['draw_type']} Draw Ending Soon!",
                    body=f"Only {time_str} left to buy your ticket. Current pot: ₦{draw.get('total_pot', 0):,.0f}",
                    notification_type="draw_reminder"
                )

            if messages:
                await self.send_bulk_notifications(messages)
                await draws_collection.update_one(
                    {"_id": draw["_id"]},
                    {"$set": {"reminder_sent": True}}
                )

    async def save_notification(self, user_id: str, title: str, body: str, notification_type: str = "general"):
        """Save notification to database"""
        try:
            notification_doc = {
                "user_id": user_id,
                "title": title,
                "body": body,
                "type": notification_type,
                "read": False,
                "created_at": datetime.utcnow()
            }
            await notifications_collection.insert_one(notification_doc)
        except Exception as e:
            print(f"Error saving notification: {e}")