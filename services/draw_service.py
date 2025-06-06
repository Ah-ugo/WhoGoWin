import asyncio
import random
from datetime import datetime, timedelta
from typing import List, Dict
from bson import ObjectId

from database import (
    draws_collection,
    tickets_collection,
    users_collection,
    platform_wallet_collection
)
from services.wallet_service import WalletService
from services.notification_service import NotificationService

class DrawService:
    def __init__(self):
        self.wallet_service = WalletService()
        self.notification_service = NotificationService()

    async def start_draw_scheduler(self):
        """Start the background task to check for completed draws"""
        while True:
            try:
                await self.check_completed_draws()
                await self.create_scheduled_draws()
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                print(f"Error in draw scheduler: {e}")
                await asyncio.sleep(60)

    async def check_completed_draws(self):
        """Check for draws that have ended and complete them"""
        current_time = datetime.utcnow()

        expired_draws = await draws_collection.find({
            "status": "active",
            "end_time": {"$lte": current_time}
        }).to_list(100)

        for draw in expired_draws:
            try:
                await self.complete_draw(str(draw["_id"]))
            except Exception as e:
                print(f"Error completing draw {draw['_id']}: {e}")

    async def complete_draw(self, draw_id: str):
        """Complete a draw and select winners"""
        draw = await draws_collection.find_one({"_id": ObjectId(draw_id)})
        if not draw or draw["status"] != "active":
            raise ValueError("Draw not found or not active")

        tickets = await tickets_collection.find({"draw_id": draw_id}).to_list(1000)

        if not tickets:
            await draws_collection.update_one(
                {"_id": ObjectId(draw_id)},
                {"$set": {"status": "completed"}}
            )
            return

        total_pot = draw.get("total_pot", 0.0)

        platform_cut = total_pot * 0.40
        first_place_prize = total_pot * 0.50
        consolation_pool = total_pot * 0.10

        winners = await self.select_winners(tickets, first_place_prize, consolation_pool)

        await draws_collection.update_one(
            {"_id": ObjectId(draw_id)},
            {
                "$set": {
                    "status": "completed",
                    "first_place_winner": winners["first_place"],
                    "consolation_winners": winners["consolation"],
                    "platform_earnings": platform_cut,
                    "completed_at": datetime.utcnow()
                }
            }
        )

        await platform_wallet_collection.update_one(
            {"_id": "platform"},
            {
                "$inc": {
                    "total_earnings": platform_cut,
                    "current_balance": platform_cut
                }
            },
            upsert=True
        )

        await self.distribute_prizes(winners, draw_id)
        await self.send_draw_completion_notifications(draw, winners)

    async def cancel_draw(self, draw_id: str):
        """Cancel a draw and refund tickets"""
        draw = await draws_collection.find_one({"_id": ObjectId(draw_id)})
        if not draw or draw["status"] != "active":
            raise ValueError("Draw not found or not active")

        tickets = await tickets_collection.find({"draw_id": draw_id}).to_list(1000)
        total_refunded = 0.0

        for ticket in tickets:
            ticket_price = ticket.get("ticket_price", 0.0)
            user_id = ticket["user_id"]
            await self.wallet_service.credit_wallet(
                user_id,
                ticket_price,
                f"Refund for cancelled draw {draw_id}"
            )
            total_refunded += ticket_price

        await tickets_collection.update_many(
            {"draw_id": draw_id},
            {"$set": {"status": "cancelled", "refunded": True}}
        )

        await draws_collection.update_one(
            {"_id": ObjectId(draw_id)},
            {
                "$set": {
                    "status": "cancelled",
                    "total_pot": 0.0,
                    "platform_earnings": 0.0,
                    "cancelled_at": datetime.utcnow()
                }
            }
        )

        for ticket in tickets:
            user = await users_collection.find_one({"_id": ObjectId(ticket["user_id"])})
            if user.get("push_token"):
                await self.notification_service.send_push_notification(
                    user["push_token"],
                    "Draw Cancelled",
                    f"The {draw['draw_type']} draw has been cancelled. Your ticket price of ₦{ticket.get('ticket_price', 0.0):,.0f} has been refunded."
                )

    async def select_winners(self, tickets: List[Dict], first_place_prize: float, consolation_pool: float) -> Dict:
        """Select winners from tickets"""
        if not tickets:
            return {"first_place": None, "consolation": []}

        first_place_ticket = random.choice(tickets)
        first_place_user = await users_collection.find_one(
            {"_id": ObjectId(first_place_ticket["user_id"])}
        )

        first_place_winner = {
            "user_id": first_place_ticket["user_id"],
            "name": first_place_user["name"],
            "prize_amount": first_place_prize
        }

        remaining_tickets = [t for t in tickets if t["_id"] != first_place_ticket["_id"]]
        consolation_winners = []

        if remaining_tickets and consolation_pool > 0:
            num_consolation = min(5, len(remaining_tickets))
            consolation_tickets = random.sample(remaining_tickets, num_consolation)
            consolation_prize_each = consolation_pool / num_consolation

            for ticket in consolation_tickets:
                user = await users_collection.find_one(
                    {"_id": ObjectId(ticket["user_id"])}
                )
                consolation_winners.append({
                    "user_id": ticket["user_id"],
                    "name": user["name"],
                    "prize_amount": consolation_prize_each
                })

        return {
            "first_place": first_place_winner,
            "consolation": consolation_winners
        }

    async def distribute_prizes(self, winners: Dict, draw_id: str):
        """Distribute prizes to winners and update tickets"""
        if winners["first_place"]:
            winner = winners["first_place"]
            await self.wallet_service.credit_wallet(
                winner["user_id"],
                winner["prize_amount"],
                f"First place prize - Draw {draw_id}"
            )

            await tickets_collection.update_one(
                {"user_id": winner["user_id"], "draw_id": draw_id},
                {
                    "$set": {
                        "is_winner": True,
                        "prize_amount": winner["prize_amount"],
                        "status": "completed"
                    }
                }
            )

        for winner in winners["consolation"]:
            await self.wallet_service.credit_wallet(
                winner["user_id"],
                winner["prize_amount"],
                f"Consolation prize - Draw {draw_id}"
            )

            await tickets_collection.update_one(
                {"user_id": winner["user_id"], "draw_id": draw_id},
                {
                    "$set": {
                        "is_winner": True,
                        "prize_amount": winner["prize_amount"],
                        "status": "completed"
                    }
                }
            )

        await tickets_collection.update_many(
            {
                "draw_id": draw_id,
                "is_winner": {"$ne": True}
            },
            {"$set": {"status": "completed"}}
        )

    async def send_draw_completion_notifications(self, draw: Dict, winners: Dict):
        """Send notifications about draw completion"""
        if winners["first_place"]:
            winner_user = await users_collection.find_one(
                {"_id": ObjectId(winners["first_place"]["user_id"])}
            )
            if winner_user.get("push_token"):
                await self.notification_service.send_push_notification(
                    winner_user["push_token"],
                    "🎉 Congratulations! You Won First Place!",
                    f"You won ₦{winners['first_place']['prize_amount']:,.0f} in the {draw['draw_type']} draw!"
                )

        for winner in winners["consolation"]:
            winner_user = await users_collection.find_one(
                {"_id": ObjectId(winner["user_id"])}
            )
            if winner_user.get("push_token"):
                await self.notification_service.send_push_notification(
                    winner_user["push_token"],
                    "🎉 You Won a Consolation Prize!",
                    f"You won ₦{winner['prize_amount']:,.0f} in the {draw['draw_type']} draw!"
                )

    async def create_scheduled_draws(self):
        """Create scheduled draws if they don't exist"""
        current_time = datetime.utcnow()

        today_daily = await draws_collection.find_one({
            "draw_type": "Daily",
            "start_time": {
                "$gte": current_time.replace(hour=0, minute=0, second=0, microsecond=0)
            }
        })

        if not today_daily:
            end_time = current_time.replace(hour=23, minute=59, second=59, microsecond=0)
            if end_time > current_time:
                await draws_collection.insert_one({
                    "draw_type": "Daily",
                    "start_time": current_time,
                    "end_time": end_time,
                    "total_pot": 0.0,
                    "status": "active",
                    "created_at": current_time,
                    "auto_created": True
                })

        week_start = current_time - timedelta(days=current_time.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

        this_week_draw = await draws_collection.find_one({
            "draw_type": "Weekly",
            "start_time": {"$gte": week_start}
        })

        if not this_week_draw:
            end_time = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
            if end_time > current_time:
                await draws_collection.insert_one({
                    "draw_type": "Weekly",
                    "start_time": current_time,
                    "end_time": end_time,
                    "total_pot": 0.0,
                    "status": "active",
                    "created_at": current_time,
                    "auto_created": True
                })

        month_start = current_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        this_month_draw = await draws_collection.find_one({
            "draw_type": "Monthly",
            "start_time": {"$gte": month_start}
        })

        if not this_month_draw:
            if current_time.month == 12:
                next_month = current_time.replace(year=current_time.year + 1, month=1, day=1)
            else:
                next_month = current_time.replace(month=current_time.month + 1, day=1)

            end_time = next_month - timedelta(seconds=1)

            if end_time > current_time:
                await draws_collection.insert_one({
                    "draw_type": "Monthly",
                    "start_time": current_time,
                    "end_time": end_time,
                    "total_pot": 0.0,
                    "status": "active",
                    "created_at": current_time,
                    "auto_created": True
                })