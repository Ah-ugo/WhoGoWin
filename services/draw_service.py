import asyncio
import random
from datetime import datetime, timedelta
from typing import List, Dict
from bson import ObjectId
import logging

from database import (
    draws_collection,
    tickets_collection,
    users_collection,
    platform_wallet_collection
)
from services.wallet_service import WalletService
from services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class DrawService:
    def __init__(self):
        self.wallet_service = WalletService()
        self.notification_service = NotificationService()
        self.base_ticket_price = 100.0  # Base price for one ticket in ₦

    async def generate_winning_numbers(self) -> List[int]:
        """Generate 5 unique random numbers between 1-30"""
        return sorted(random.sample(range(1, 31), 5))

    async def calculate_matches(self, ticket_numbers: List[int], winning_numbers: List[int]) -> int:

        """Calculate how many numbers match between ticket and winning numbers"""
        return len(set(ticket_numbers) & set(winning_numbers))


    async def purchase_ticket(self, user_id: str, draw_id: str, ticket_price: float, selected_numbers: List[int]) -> \
    List[str]:
        """Purchase a ticket with selected numbers"""
        if ticket_price < self.base_ticket_price:
            raise ValueError(f"Ticket price must be at least ₦{self.base_ticket_price}")

        if len(selected_numbers) != 5 or len(set(selected_numbers)) != 5:
            raise ValueError("Exactly 5 unique numbers must be selected")

        if not all(1 <= num <= 30 for num in selected_numbers):
            raise ValueError("Numbers must be between 1 and 30")

        # Calculate number of virtual tickets
        ticket_count = int(ticket_price / self.base_ticket_price)
        current_time = datetime.utcnow()

        # Create ticket entries
        ticket_ids = []
        for _ in range(ticket_count):
            ticket = {
                "user_id": user_id,
                "draw_id": draw_id,
                "ticket_price": self.base_ticket_price,
                "selected_numbers": selected_numbers,
                "status": "active",
                "created_at": current_time,
                "is_winner": False,
                "prize_amount": None,
                "match_count": None
            }
            result = await tickets_collection.insert_one(ticket)
            ticket_ids.append(str(result.inserted_id))

        # Update draw's total pot
        await draws_collection.update_one(
            {"_id": ObjectId(draw_id)},
            {"$inc": {"total_pot": ticket_price, "total_tickets": ticket_count}}
        )

        # Debit user's wallet
        await self.wallet_service.debit_wallet(
            user_id,
            ticket_price,
            f"Ticket purchase for draw {draw_id}"
        )

        return ticket_ids

    async def start_draw_scheduler(self):
        """Start the background task to check for completed draws"""
        while True:
            try:
                await self.check_completed_draws()
                await self.create_scheduled_draws()
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Error in draw scheduler: {e}")
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
                logger.error(f"Error completing draw {draw['_id']}: {e}")

    async def complete_draw(self, draw_id: str):
        """Complete a draw with number matching"""
        draw = await draws_collection.find_one({"_id": ObjectId(draw_id)})
        if not draw or draw["status"] != "active":
            raise ValueError("Draw not found or not active")

        # Generate winning numbers (5 unique numbers between 1-30)
        winning_numbers = sorted(random.sample(range(1, 31), 5))

        tickets = await tickets_collection.find({"draw_id": draw_id}).to_list(1000)
        if not tickets:
            await draws_collection.update_one(
                {"_id": ObjectId(draw_id)},
                {"$set": {
                    "status": "completed",
                    "winning_numbers": winning_numbers,
                    "completed_at": datetime.utcnow()
                }}
            )
            return

        total_pot = draw.get("total_pot", 0.0)
        platform_cut = total_pot * 0.10  # Platform gets 10%

        # Initialize prize pools
        prize_pools = {
            5: {"amount": total_pot * 0.50, "winners": []},  # 50% for 5 matches
            4: {"amount": total_pot * 0.20, "winners": []},  # 20% for 4 matches
            3: {"amount": total_pot * 0.15, "winners": []},  # 15% for 3 matches
            2: {"amount": total_pot * 0.05, "winners": []},  # 5% for 2 matches
        }

        # Calculate matches for all tickets
        for ticket in tickets:
            match_count = await self.calculate_matches(
                ticket.get("selected_numbers", []),
                winning_numbers
            )
            await tickets_collection.update_one(
                {"_id": ticket["_id"]},
                {"$set": {"match_count": match_count}}
            )
            if match_count >= 2:  # Only count matches of 2 or more
                prize_pools[match_count]["winners"].append({
                    "user_id": ticket["user_id"],
                    "ticket_id": str(ticket["_id"])
                })

        # Calculate prize amounts per winner in each tier
        winners = []
        for match_count, pool in prize_pools.items():
            if pool["winners"]:
                prize_per_winner = round(pool["amount"] / len(pool["winners"]), 2)
                for winner in pool["winners"]:
                    winners.append({
                        "user_id": winner["user_id"],
                        "ticket_id": winner["ticket_id"],
                        "match_count": match_count,
                        "prize_amount": prize_per_winner
                    })

        # Update draw with winners and winning numbers
        await draws_collection.update_one(
            {"_id": ObjectId(draw_id)},
            {"$set": {
                "status": "completed",
                "winning_numbers": winning_numbers,  # Ensure this is set
                "platform_earnings": platform_cut,
                "completed_at": datetime.utcnow()
            }}
        )

        # Rest of the method remains the same...
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
        await self.send_draw_completion_notifications(draw, winners, winning_numbers)


    async def distribute_prizes(self, winners: List[dict], draw_id: str):
        """Distribute prizes to winners"""
        for winner in winners:
            # Credit winner's wallet
            await self.wallet_service.credit_wallet(
                winner["user_id"],
                winner["prize_amount"],
                f"Prize for {winner['match_count']} matches in draw {draw_id}"
            )

            # Update winner's ticket
            await tickets_collection.update_one(
                {"_id": ObjectId(winner["ticket_id"])},
                {
                    "$set": {
                        "is_winner": True,
                        "prize_amount": winner["prize_amount"],
                        "status": "completed"
                    }
                }
            )

        # Update all non-winning tickets
        await tickets_collection.update_many(
            {
                "draw_id": draw_id,
                "is_winner": {"$ne": True}
            },
            {"$set": {"status": "completed"}}
        )

    async def send_draw_completion_notifications(self, draw: dict, winners: List[dict], winning_numbers: List[int]):
        """Send notifications about draw completion"""
        # Notify all winners
        for winner in winners:
            user = await users_collection.find_one({"_id": ObjectId(winner["user_id"])})
            if user and user.get("push_token"):
                await self.notification_service.send_push_notification(
                    user["push_token"],
                    f"🎉 You matched {winner['match_count']} numbers!",
                    f"You won ₦{winner['prize_amount']:,.2f} in the {draw['draw_type']} draw! Winning numbers: {', '.join(map(str, winning_numbers))}"
                )
                await self.notification_service.save_notification(
                    user_id=winner["user_id"],
                    title=f"You matched {winner['match_count']} numbers!",
                    body=f"You won ₦{winner['prize_amount']:,.2f} in the {draw['draw_type']} draw!",
                    notification_type="draw_win"
                )

        # Notify all participants about draw completion
        participants = await tickets_collection.distinct("user_id", {"draw_id": str(draw["_id"])})
        for user_id in participants:
            user = await users_collection.find_one({"_id": ObjectId(user_id)})
            if user and user.get("push_token"):
                await self.notification_service.send_push_notification(
                    user["push_token"],
                    f"{draw['draw_type']} Draw Completed",
                    f"The {draw['draw_type']} draw has been completed. Winning numbers: {', '.join(map(str, winning_numbers))}"
                )

    async def cancel_draw(self, draw_id: str):
        """Cancel a draw and refund tickets"""
        draw = await draws_collection.find_one({"_id": ObjectId(draw_id)})
        if not draw or draw["status"] != "active":
            raise ValueError("Draw not found or not active")

        tickets = await tickets_collection.find({"draw_id": draw_id}).to_list(1000)
        total_refunded = 0.0

        # Group tickets by user to calculate total refund per user
        user_tickets = {}
        for ticket in tickets:
            user_id = ticket["user_id"]
            ticket_price = ticket.get("ticket_price", self.base_ticket_price)
            user_tickets[user_id] = user_tickets.get(user_id, 0.0) + ticket_price
            total_refunded += ticket_price

        for user_id, refund_amount in user_tickets.items():
            await self.wallet_service.credit_wallet(
                user_id,
                refund_amount,
                f"Refund for cancelled draw {draw_id}"
            )

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

        # Notify all participants
        for user_id in user_tickets:
            user = await users_collection.find_one({"_id": ObjectId(user_id)})
            if user and user.get("push_token"):
                await self.notification_service.send_push_notification(
                    user["push_token"],
                    "Draw Cancelled",
                    f"The {draw['draw_type']} draw has been cancelled. Your ticket price of ₦{user_tickets[user_id]:,.0f} has been refunded."
                )

    async def create_scheduled_draws(self):
        """Create scheduled draws if they don't exist"""
        current_time = datetime.utcnow()

        # Daily draw
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
                    "total_tickets": 0,
                    "status": "active",
                    "created_at": current_time,
                    "auto_created": True
                })

        # Weekly draw
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
                    "total_tickets": 0,
                    "status": "active",
                    "created_at": current_time,
                    "auto_created": True
                })

        # Monthly draw
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
                    "total_tickets": 0,
                    "status": "active",
                    "created_at": current_time,
                    "auto_created": True
                })