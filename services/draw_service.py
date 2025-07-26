import asyncio
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pymongo.client_session import ClientSession
from bson import ObjectId
import logging

from database import (
    draws_collection,
    tickets_collection,
    users_collection,
    platform_wallet_collection,
transactions_collection,
client
)
from services.wallet_service import WalletService
from services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class DrawService:
    def __init__(self):
        self.wallet_service = WalletService()
        self.notification_service = NotificationService()
        self.base_ticket_price = 100.0
        self.min_matches_to_win = 2

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

    async def complete_draw(self, draw_id: str) -> Dict:
        """Complete a draw with comprehensive error handling"""
        try:
            async with await client.start_session() as session:
                async with session.start_transaction():
                    # Get the draw document
                    draw = await draws_collection.find_one(
                        {"_id": ObjectId(draw_id)},
                        session=session
                    )
                    if not draw:
                        logger.error(f"Draw {draw_id} not found")
                        return {"success": False, "message": "Draw not found"}

                    if draw["status"] != "active":
                        logger.error(f"Draw {draw_id} is not active")
                        return {"success": False, "message": "Draw is not active"}

                    # Generate winning numbers
                    winning_numbers = sorted(random.sample(range(1, 31), 5))
                    logger.info(f"Winning numbers: {winning_numbers}")

                    # Get all tickets
                    tickets = await tickets_collection.find(
                        {"draw_id": draw_id},
                        session=session
                    ).to_list(None)

                    total_pot = draw.get("total_pot", 0.0)
                    platform_cut = total_pot * 0.10
                    winners = []

                    if tickets:
                        # Initialize prize pools
                        prize_pools = {
                            5: {"amount": total_pot * 0.50, "winners": []},  # 50% for 5 matches
                            4: {"amount": total_pot * 0.20, "winners": []},  # 20% for 4 matches
                            3: {"amount": total_pot * 0.15, "winners": []},  # 15% for 3 matches
                            2: {"amount": total_pot * 0.05, "winners": []},  # 5% for 2 matches
                        }

                        # Process each ticket
                        for ticket in tickets:
                            ticket_numbers = ticket.get("selected_numbers", [])
                            if not ticket_numbers or len(ticket_numbers) != 5:
                                continue  # Skip invalid tickets

                            match_count = len(set(ticket_numbers) & set(winning_numbers))

                            # Update ticket with match count
                            await tickets_collection.update_one(
                                {"_id": ticket["_id"]},
                                {"$set": {"match_count": match_count}},
                                session=session
                            )

                            if match_count >= self.min_matches_to_win:
                                prize_pools[match_count]["winners"].append(ticket)
                                prize_per_winner = round(
                                    prize_pools[match_count]["amount"] /
                                    len(prize_pools[match_count]["winners"]),
                                    2
                                )
                                winners.append({
                                    "user_id": ticket["user_id"],
                                    "ticket_id": str(ticket["_id"]),
                                    "match_count": match_count,
                                    "prize_amount": prize_per_winner
                                })

                        # Distribute prizes
                        for winner in winners:
                            await self.wallet_service.credit_wallet(
                                winner["user_id"],
                                winner["prize_amount"],
                                f"Prize for {winner['match_count']} matches",
                                session=session
                            )
                            await tickets_collection.update_one(
                                {"_id": ObjectId(winner["ticket_id"])},
                                {
                                    "$set": {
                                        "is_winner": True,
                                        "prize_amount": winner["prize_amount"],
                                        "status": "completed"
                                    }
                                },
                                session=session
                            )

                    # Update platform wallet
                    await platform_wallet_collection.update_one(
                        {"_id": "platform"},
                        {
                            "$inc": {
                                "total_earnings": platform_cut,
                                "current_balance": platform_cut
                            }
                        },
                        session=session,
                        upsert=True
                    )

                    # Categorize winners
                    first_place = [w for w in winners if w["match_count"] == 5]
                    consolation = [w for w in winners if self.min_matches_to_win <= w["match_count"] < 5]

                    # Update the draw document
                    update_result = await draws_collection.update_one(
                        {"_id": ObjectId(draw_id)},
                        {
                            "$set": {
                                "status": "completed",
                                "winning_numbers": winning_numbers,
                                "first_place_winner": first_place[0] if first_place else None,
                                "consolation_winners": consolation,
                                "platform_earnings": platform_cut,
                                "completed_at": datetime.utcnow()
                            }
                        },
                        session=session
                    )

                    if update_result.modified_count == 0:
                        logger.error("Failed to update draw document")
                        await session.abort_transaction()
                        return {"success": False, "message": "Failed to update draw"}

                    await session.commit_transaction()
                    logger.info(f"Successfully completed draw {draw_id}")

                    return {
                        "success": True,
                        "message": "Draw completed successfully",
                        "draw_id": draw_id,
                        "winning_numbers": winning_numbers,
                        "first_place_winner": first_place[0] if first_place else None,
                        "consolation_winners_count": len(consolation),
                        "platform_earnings": platform_cut
                    }

        except Exception as e:
            logger.error(f"Error completing draw {draw_id}: {str(e)}")
            return {"success": False, "message": f"Error: {str(e)}"}


    async def get_draw_with_winners(self, draw_id: str):
        """Get draw with populated winner information"""
        draw = await draws_collection.find_one({"_id": ObjectId(draw_id)})
        if not draw:
            return None

        # Populate winner details
        if draw.get("first_place_winner"):
            user = await users_collection.find_one(
                {"_id": ObjectId(draw["first_place_winner"]["user_id"])}
            )
            if user:
                draw["first_place_winner"]["user_name"] = user.get("name", "Unknown")

        for winner in draw.get("consolation_winners", []):
            user = await users_collection.find_one(
                {"_id": ObjectId(winner["user_id"])}
            )
            if user:
                winner["user_name"] = user.get("name", "Unknown")

        return draw

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

    async def send_draw_completion_notifications(
            self,
            draw: dict,
            winners: List[dict],
            winning_numbers: List[int],
            session: Optional[ClientSession] = None
    ):
        """Enhanced notification system with session support"""
        try:
            # Notify winners
            for winner in winners:
                user = await users_collection.find_one(
                    {"_id": ObjectId(winner["user_id"])},
                    {"push_token": 1, "name": 1},
                    session=session
                )
                if user:
                    message = (
                        f"Congratulations {user.get('name', 'Winner')}! "
                        f"You matched {winner['match_count']} numbers and won "
                        f"₦{winner['prize_amount']:,.2f}!"
                    )

                    if user.get("push_token"):
                        await self.notification_service.send_push_notification(
                            user["push_token"],
                            "🎉 You Won!",
                            message
                        )

                    await self.notification_service.save_notification(
                        user_id=winner["user_id"],
                        title="You Won!",
                        body=message,
                        notification_type="draw_win",
                        session=session
                    )

            # Notify all participants
            participants = await tickets_collection.distinct(
                "user_id",
                {"draw_id": str(draw["_id"])},
                session=session
            )

            for user_id in participants:
                user = await users_collection.find_one(
                    {"_id": ObjectId(user_id)},
                    {"push_token": 1, "name": 1},
                    session=session
                )
                if user:
                    is_winner = any(w["user_id"] == user_id for w in winners)
                    if not is_winner and user.get("push_token"):
                        await self.notification_service.send_push_notification(
                            user["push_token"],
                            f"{draw['draw_type']} Draw Completed",
                            f"The draw has completed. Winning numbers: {', '.join(map(str, winning_numbers))}"
                        )

        except Exception as e:
            logger.error(f"Error sending notifications: {str(e)}", exc_info=True)

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