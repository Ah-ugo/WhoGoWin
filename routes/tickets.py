from fastapi import APIRouter, HTTPException, Depends, status
from typing import List
from datetime import datetime
from bson import ObjectId

from models.ticket import TicketCreate, TicketResponse, TicketUpdate
from routes.auth import get_current_user, get_current_admin_user
from database import tickets_collection, draws_collection, users_collection, transactions_collection
from services.wallet_service import WalletService
from services.notification_service import NotificationService

router = APIRouter()
wallet_service = WalletService()
notification_service = NotificationService()

@router.post("/buy", response_model=TicketResponse)
async def buy_ticket(
        ticket_data: TicketCreate,
        current_user: dict = Depends(get_current_user)
):
    """Buy a lottery ticket"""
    try:
        draw = await draws_collection.find_one({"_id": ObjectId(ticket_data.draw_id)})
        if not draw:
            raise HTTPException(status_code=404, detail="Draw not found")

        if draw["status"] != "active":
            raise HTTPException(status_code=400, detail="Draw is not active")

        if datetime.utcnow() >= draw["end_time"]:
            raise HTTPException(status_code=400, detail="Draw has ended")

    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid draw ID")

    user_balance = current_user.get("wallet_balance", 0.0)
    if user_balance < ticket_data.ticket_price:
        raise HTTPException(
            status_code=400,
            detail="Insufficient wallet balance"
        )

    await wallet_service.debit_wallet(
        str(current_user["_id"]),
        ticket_data.ticket_price,
        f"Ticket purchase for {draw['draw_type']} draw"
    )

    ticket_doc = {
        "user_id": str(current_user["_id"]),
        "draw_id": ticket_data.draw_id,
        "draw_type": draw["draw_type"],
        "ticket_price": ticket_data.ticket_price,
        "purchase_date": datetime.utcnow(),
        "status": "active",
        "is_winner": False,
        "prize_amount": None
    }

    result = await tickets_collection.insert_one(ticket_doc)
    ticket_doc["_id"] = result.inserted_id

    await draws_collection.update_one(
        {"_id": ObjectId(ticket_data.draw_id)},
        {"$inc": {"total_pot": ticket_data.ticket_price}}
    )

    return TicketResponse(
        id=str(ticket_doc["_id"]),
        user_id=ticket_doc["user_id"],
        draw_id=ticket_doc["draw_id"],
        draw_type=ticket_doc["draw_type"],
        ticket_price=ticket_doc["ticket_price"],
        purchase_date=ticket_doc["purchase_date"],
        status=ticket_doc["status"],
        is_winner=ticket_doc["is_winner"],
        prize_amount=ticket_doc["prize_amount"]
    )

@router.get("/my-tickets", response_model=List[TicketResponse])
async def get_my_tickets(current_user: dict = Depends(get_current_user)):
    """Get current user's tickets"""
    tickets = await tickets_collection.find(
        {"user_id": str(current_user["_id"])}
    ).sort("purchase_date", -1).to_list(100)

    result = []
    for ticket in tickets:
        result.append(TicketResponse(
            id=str(ticket["_id"]),
            user_id=ticket["user_id"],
            draw_id=ticket["draw_id"],
            draw_type=ticket["draw_type"],
            ticket_price=ticket["ticket_price"],
            purchase_date=ticket["purchase_date"],
            status=ticket["status"],
            is_winner=ticket.get("is_winner", False),
            prize_amount=ticket.get("prize_amount")
        ))

    return result

@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
        ticket_id: str,
        current_user: dict = Depends(get_current_user)
):
    """Get specific ticket details"""
    try:
        ticket = await tickets_collection.find_one({"_id": ObjectId(ticket_id)})
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        if ticket["user_id"] != str(current_user["_id"]):
            raise HTTPException(status_code=403, detail="Access denied")

        return TicketResponse(
            id=str(ticket["_id"]),
            user_id=ticket["user_id"],
            draw_id=ticket["draw_id"],
            draw_type=ticket["draw_type"],
            ticket_price=ticket["ticket_price"],
            purchase_date=ticket["purchase_date"],
            status=ticket["status"],
            is_winner=ticket.get("is_winner", False),
            prize_amount=ticket.get("prize_amount")
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid ticket ID")

@router.get("/list/all", response_model=List[TicketResponse])
async def get_all_tickets(
        current_user: dict = Depends(get_current_admin_user)
):
    """Get all tickets in the system (Admin only)"""
    tickets = await tickets_collection.find().sort("purchase_date", -1).to_list(1000)

    result = []
    for ticket in tickets:
        result.append(TicketResponse(
            id=str(ticket["_id"]),
            user_id=ticket["user_id"],
            draw_id=ticket["draw_id"],
            draw_type=ticket["draw_type"],
            ticket_price=ticket["ticket_price"],
            purchase_date=ticket["purchase_date"],
            status=ticket["status"],
            is_winner=ticket.get("is_winner", False),
            prize_amount=ticket.get("prize_amount")
        ))
    return result

@router.get("/draw/{draw_id}", response_model=List[TicketResponse])
async def get_tickets_by_draw(
        draw_id: str,
        current_user: dict = Depends(get_current_admin_user)
):
    """Get all tickets for a specific draw (Admin only)"""
    try:
        draw = await draws_collection.find_one({"_id": ObjectId(draw_id)})
        if not draw:
            raise HTTPException(status_code=404, detail="Draw not found")

        tickets = await tickets_collection.find(
            {"draw_id": draw_id}
        ).sort("purchase_date", -1).to_list(1000)

        result = []
        for ticket in tickets:
            result.append(TicketResponse(
                id=str(ticket["_id"]),
                user_id=ticket["user_id"],
                draw_id=ticket["draw_id"],
                draw_type=ticket["draw_type"],
                ticket_price=ticket["ticket_price"],
                purchase_date=ticket["purchase_date"],
                status=ticket["status"],
                is_winner=ticket.get("is_winner", False),
                prize_amount=ticket.get("prize_amount")
            ))
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid draw ID")

@router.get("/user/{user_id}", response_model=List[TicketResponse])
async def get_tickets_by_user(
        user_id: str,
        current_user: dict = Depends(get_current_admin_user)
):
    """Get all tickets for a specific user (Admin only)"""
    try:
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        tickets = await tickets_collection.find(
            {"user_id": user_id}
        ).sort("purchase_date", -1).to_list(1000)

        result = []
        for ticket in tickets:
            result.append(TicketResponse(
                id=str(ticket["_id"]),
                user_id=ticket["user_id"],
                draw_id=ticket["draw_id"],
                draw_type=ticket["draw_type"],
                ticket_price=ticket["ticket_price"],
                purchase_date=ticket["purchase_date"],
                status=ticket["status"],
                is_winner=ticket.get("is_winner", False),
                prize_amount=ticket.get("prize_amount")
            ))
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid user ID")

@router.put("/{ticket_id}/update", response_model=TicketResponse)
async def update_ticket(
        ticket_id: str,
        ticket_update: TicketUpdate,
        current_user: dict = Depends(get_current_admin_user)
):
    """Update ticket details (Admin only)"""
    try:
        ticket = await tickets_collection.find_one({"_id": ObjectId(ticket_id)})
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        update_data = {}
        if ticket_update.status is not None:
            update_data["status"] = ticket_update.status
        if ticket_update.is_winner is not None:
            update_data["is_winner"] = ticket_update.is_winner
        if ticket_update.prize_amount is not None:
            update_data["prize_amount"] = ticket_update.prize_amount

        if not update_data:
            raise HTTPException(status_code=400, detail="No updates provided")

        await tickets_collection.update_one(
            {"_id": ObjectId(ticket_id)},
            {"$set": update_data}
        )

        updated_ticket = await tickets_collection.find_one({"_id": ObjectId(ticket_id)})
        return TicketResponse(
            id=str(updated_ticket["_id"]),
            user_id=updated_ticket["user_id"],
            draw_id=updated_ticket["draw_id"],
            draw_type=updated_ticket["draw_type"],
            ticket_price=updated_ticket["ticket_price"],
            purchase_date=updated_ticket["purchase_date"],
            status=updated_ticket["status"],
            is_winner=updated_ticket.get("is_winner", False),
            prize_amount=updated_ticket.get("prize_amount")
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid ticket ID or update data")

@router.post("/{ticket_id}/refund", response_model=dict)
async def refund_ticket(
        ticket_id: str,
        current_user: dict = Depends(get_current_admin_user)
):
    """Refund a ticket and notify the user (Admin only)"""
    try:
        ticket = await tickets_collection.find_one({"_id": ObjectId(ticket_id)})
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        if ticket["status"] != "active":
            raise HTTPException(status_code=400, detail="Can only refund active tickets")

        draw = await draws_collection.find_one({"_id": ObjectId(ticket["draw_id"])})
        if not draw:
            raise HTTPException(status_code=404, detail="Draw not found")

        user = await users_collection.find_one({"_id": ObjectId(ticket["user_id"])})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Refund the ticket price
        await wallet_service.credit_wallet(
            ticket["user_id"],
            ticket["ticket_price"],
            f"Refund for ticket {ticket_id} in {draw['draw_type']} draw"
        )

        # Update ticket status
        await tickets_collection.update_one(
            {"_id": ObjectId(ticket_id)},
            {
                "$set": {
                    "status": "refunded",
                    "refunded": True,
                    "refunded_at": datetime.utcnow()
                }
            }
        )

        # Update draw total pot
        await draws_collection.update_one(
            {"_id": ObjectId(ticket["draw_id"])},
            {"$inc": {"total_pot": -ticket["ticket_price"]}}
        )

        # Notify user
        if user.get("push_token"):
            await notification_service.send_push_notification(
                user["push_token"],
                "Ticket Refunded",
                f"Your ticket for the {draw['draw_type']} draw has been refunded. Amount: ₦{ticket['ticket_price']:,.0f}"
            )

        # Save notification
        await notification_service.save_notification(
            user_id=ticket["user_id"],
            title="Ticket Refunded",
            body=f"Your ticket for the {draw['draw_type']} draw has been refunded. Amount: ₦{ticket['ticket_price']:,.0f}",
            notification_type="refund"
        )

        return {"message": "Ticket refunded successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid ticket ID or refund failed")