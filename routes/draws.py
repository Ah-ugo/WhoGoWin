from fastapi import APIRouter, HTTPException, Depends, status
from typing import List
from datetime import datetime, timedelta
from bson import ObjectId

from models.draw import DrawCreate, DrawResponse, DrawUpdate, DrawStatus
from models.user import UserResponse, Role
from routes.auth import get_current_user, get_current_admin_user
from database import draws_collection, tickets_collection, users_collection
# from services import notification_service
from services.draw_service import DrawService
from services.notification_service import NotificationService
import logging
import pytz

router = APIRouter()
draw_service = DrawService()

notification_service = NotificationService()
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@router.get("/active", response_model=List[DrawResponse])
async def get_active_draws():
    """Get all active draws"""
    draws = await draws_collection.find({"status": "active"}).to_list(100)
    result = []
    for draw in draws:
        try:
            draw_data = {
                "id": str(draw["_id"]),
                "draw_type": draw.get("draw_type", "Unknown"),
                "start_time": draw.get("start_time", datetime.utcnow()),
                "end_time": draw.get("end_time", datetime.utcnow() + timedelta(days=1)),
                "total_pot": float(draw.get("total_pot", 0.0)),
                "total_tickets": 0,
                "status": draw.get("status", "active"),
                "first_place_winner": None,
                "consolation_winners": [],
                "platform_earnings": float(draw.get("platform_earnings", 0.0)),
                "created_at": draw.get("created_at", datetime.utcnow())
            }
            if "first_place_winner" in draw and isinstance(draw["first_place_winner"], dict):
                draw_data["first_place_winner"] = draw["first_place_winner"].get("user_id")
            if "consolation_winners" in draw and isinstance(draw["consolation_winners"], list):
                draw_data["consolation_winners"] = [
                    winner.get("user_id") if isinstance(winner, dict) else winner
                    for winner in draw["consolation_winners"]
                ]
            ticket_count = await tickets_collection.count_documents({"draw_id": str(draw["_id"])})
            draw_data["total_tickets"] = ticket_count
            result.append(DrawResponse(**draw_data))
        except Exception as e:
            logger.warning(f"Skipping invalid draw {str(draw['_id'])}: {str(e)}")
            continue
    return result

# @router.get("/completed", response_model=List[DrawResponse])
# async def get_completed_draws():
#     """Get completed draws with results"""
#     draws = await draws_collection.find(
#         {"status": "completed"}
#     ).sort("end_time", -1).limit(50).to_list(50)
#
#     result = []
#     for draw in draws:
#         ticket_count = await tickets_collection.count_documents({"draw_id": str(draw["_id"])})
#
#         result.append(DrawResponse(
#             id=str(draw["_id"]),
#             draw_type=draw["draw_type"],
#             start_time=draw["start_time"],
#             end_time=draw["end_time"],
#             total_pot=draw.get("total_pot", 0.0),
#             total_tickets=ticket_count,
#             status=draw["status"],
#             first_place_winner=draw.get("first_place_winner"),
#             consolation_winners=draw.get("consolation_winners", []),
#             platform_earnings=draw.get("platform_earnings", 0.0),
#             created_at=draw["created_at"]
#         ))
#
#     return result


@router.get("/completed", response_model=List[DrawResponse])
async def get_completed_draws():
    """Get completed draws with results"""
    draws = await draws_collection.find({"status": "completed"}).sort("end_time", -1).limit(50).to_list(50)
    result = []
    for draw in draws:
        ticket_count = await tickets_collection.count_documents({"draw_id": str(draw["_id"])})

        # Convert MongoDB's number objects to plain integers for winning_numbers
        winning_numbers = [num if isinstance(num, int) else num['$numberInt'] for num in
                           draw.get("winning_numbers", [])]

        draw_data = {
            "id": str(draw["_id"]),
            "draw_type": draw["draw_type"],
            "start_time": draw["start_time"],
            "end_time": draw["end_time"],
            "total_pot": draw.get("total_pot", 0.0),
            "total_tickets": ticket_count,
            "status": draw["status"],
            "winning_numbers": winning_numbers,
            "first_place_winner": draw.get("first_place_winner"),
            "consolation_winners": draw.get("consolation_winners", []),
            "platform_earnings": draw.get("platform_earnings", 0.0),
            "created_at": draw["created_at"]
        }
        result.append(DrawResponse(**draw_data))
    return result

@router.get("/{draw_id}", response_model=DrawResponse)
async def get_draw(draw_id: str):
    """Get specific draw details"""
    try:
        draw = await draws_collection.find_one({"_id": ObjectId(draw_id)})
        if not draw:
            raise HTTPException(status_code=404, detail="Draw not found")

        ticket_count = await tickets_collection.count_documents({"draw_id": draw_id})

        return DrawResponse(
            id=str(draw["_id"]),
            draw_type=draw["draw_type"],
            start_time=draw["start_time"],
            end_time=draw["end_time"],
            total_pot=draw.get("total_pot", 0.0),
            total_tickets=ticket_count,
            status=draw["status"],
            first_place_winner=draw.get("first_place_winner"),
            consolation_winners=draw.get("consolation_winners", []),
            platform_earnings=draw.get("platform_earnings", 0.0),
            created_at=draw["created_at"]
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid draw ID")

# @router.post("/create", response_model=DrawResponse)
# async def create_draw(
#         draw_data: DrawCreate,
#         current_user: dict = Depends(get_current_admin_user)
# ):
#     """Create a new draw (Admin only)"""
#     draw_doc = {
#         "draw_type": draw_data.draw_type,
#         "start_time": datetime.utcnow(),
#         "end_time": draw_data.end_time,
#         "total_pot": 0.0,
#         "status": "active",
#         "created_by": str(current_user["_id"]),
#         "created_at": datetime.utcnow(),
#         "first_place_winner": None,
#         "consolation_winners": [],
#         "platform_earnings": 0.0
#     }
#
#     result = await draws_collection.insert_one(draw_doc)
#     draw_doc["_id"] = result.inserted_id
#
#     return DrawResponse(
#         id=str(draw_doc["_id"]),
#         draw_type=draw_doc["draw_type"],
#         start_time=draw_doc["start_time"],
#         end_time=draw_doc["end_time"],
#         total_pot=draw_doc["total_pot"],
#         total_tickets=0,
#         status=draw_doc["status"],
#         first_place_winner=draw_doc["first_place_winner"],
#         consolation_winners=draw_doc["consolation_winners"],
#         platform_earnings=draw_doc["platform_earnings"],
#         created_at=draw_doc["created_at"]
#     )



@router.post("/create", response_model=DrawResponse)
async def create_draw(
        draw_data: DrawCreate,
        current_user: dict = Depends(get_current_admin_user)
):
    """Create a new draw (Admin only)"""
    current_time = datetime.now(pytz.UTC)
    if draw_data.end_time <= current_time:
        raise HTTPException(status_code=400, detail="End time must be in the future")

    draw_doc = {
        "draw_type": draw_data.draw_type,
        "start_time": current_time,
        "end_time": draw_data.end_time,
        "total_pot": 0.0,
        "total_tickets": 0,
        "status": "active",
        "first_place_winner": None,
        "consolation_winners": [],
        "platform_earnings": 0.0,
        "created_at": current_time
    }

    result = await draws_collection.insert_one(draw_doc)
    draw_doc["_id"] = result.inserted_id

    return DrawResponse(
        id=str(draw_doc["_id"]),
        draw_type=draw_doc["draw_type"],
        start_time=draw_doc["start_time"],
        end_time=draw_doc["end_time"],
        total_pot=draw_doc["total_pot"],
        total_tickets=draw_doc["total_tickets"],
        status=draw_doc["status"],
        first_place_winner=draw_doc["first_place_winner"],
        consolation_winners=draw_doc["consolation_winners"],
        platform_earnings=draw_doc["platform_earnings"],
        created_at=draw_doc["created_at"]
    )


@router.put("/{draw_id}/update", response_model=DrawResponse)
async def update_draw(
        draw_id: str,
        draw_update: DrawUpdate,
        current_user: dict = Depends(get_current_admin_user)
):
    """Update draw details (Admin only)"""
    try:
        draw = await draws_collection.find_one({"_id": ObjectId(draw_id)})
        if not draw:
            raise HTTPException(status_code=404, detail="Draw not found")

        update_data = draw_update.dict(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No updates provided")

        # Validate updates
        if "end_time" in update_data:
            # Ensure current time is offset-aware (UTC)
            current_time = datetime.now(pytz.UTC)
            if update_data["end_time"] <= current_time:
                raise HTTPException(status_code=400, detail="End time must be in the future")
            if draw.get("total_tickets", 0) > 0:
                raise HTTPException(status_code=400, detail="Cannot update end time after tickets are sold")
            # Ensure start_time is offset-aware (UTC)
            start_time = draw["start_time"]
            if isinstance(start_time, datetime) and start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=pytz.UTC)
            if update_data["end_time"] <= start_time:
                raise HTTPException(status_code=400, detail="End time must be after start time")

        if "status" in update_data:
            valid_statuses = ["active", "completed", "cancelled"]
            if update_data["status"] not in valid_statuses:
                raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of {valid_statuses}")
            if draw["status"] in ["completed", "cancelled"]:
                raise HTTPException(status_code=400, detail="Cannot update a completed or cancelled draw")

        # Apply updates
        await draws_collection.update_one(
            {"_id": ObjectId(draw_id)},
            {"$set": update_data}
        )

        updated_draw = await draws_collection.find_one({"_id": ObjectId(draw_id)})
        if not updated_draw:
            raise HTTPException(status_code=500, detail="Failed to retrieve updated draw")

        # Notify users if end_time or status changes
        if "end_time" in update_data or "status" in update_data:
            users_with_tokens = await draws_collection.database.users_collection.find(
                {"push_token": {"$exists": True, "$ne": None}}
            ).to_list(1000)
            for user in users_with_tokens:
                message = f"Draw {updated_draw['draw_type']} updated: "
                if "end_time" in update_data:
                    message += f"New end time is {update_data['end_time'].strftime('%Y-%m-%d %H:%M:%S UTC')}. "
                if "status" in update_data:
                    message += f"Status changed to {update_data['status']}."
                if user.get("push_token"):
                    await notification_service.send_push_notification(
                        user["push_token"],
                        "Draw Updated",
                        message
                    )
                await notification_service.save_notification(
                    user_id=str(user["_id"]),
                    title="Draw Updated",
                    body=message,
                    notification_type="draw_update"
                )

        # Prepare response
        ticket_count = await tickets_collection.count_documents({"draw_id": draw_id})
        return DrawResponse(
            id=str(updated_draw["_id"]),
            draw_type=updated_draw["draw_type"],
            start_time=updated_draw["start_time"],
            end_time=updated_draw["end_time"],
            total_pot=updated_draw.get("total_pot", 0.0),
            total_tickets=ticket_count,
            status=updated_draw["status"],
            first_place_winner=updated_draw.get("first_place_winner"),
            consolation_winners=updated_draw.get("consolation_winners", []),
            platform_earnings=updated_draw.get("platform_earnings", 0.0),
            created_at=updated_draw["created_at"]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid draw ID or update data: {str(e)}")
@router.post("/{draw_id}/complete", response_model=dict)
async def complete_draw(
        draw_id: str,
        current_user: dict = Depends(get_current_admin_user)
):
    """Manually complete a draw and select winners (Admin only)"""
    try:
        await draw_service.complete_draw(draw_id)
        return {"message": "Draw completed successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{draw_id}/cancel", response_model=dict)
async def cancel_draw(
        draw_id: str,
        current_user: dict = Depends(get_current_admin_user)
):
    """Cancel a draw and refund tickets (Admin only)"""
    try:
        await draw_service.cancel_draw(draw_id)
        return {"message": "Draw cancelled successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# @router.get("/{draw_id}", response_model=DrawResponse)
# async def get_draw(draw_id: str):
#     """Get specific draw details"""
#     try:
#         draw = await draws_collection.find_one({"_id": ObjectId(draw_id)})
#         if not draw:
#             raise HTTPException(status_code=404, detail="Draw not found")
#         return DrawResponse(**draw)
#     except Exception as e:
#         raise HTTPException(status_code=400, detail="Invalid draw ID")

@router.get("/list/all", response_model=List[DrawResponse])
async def get_all_draws(current_user: dict = Depends(get_current_admin_user)):
    """Get all draws (Admin only)"""
    try:
        draws = await draws_collection.find().sort("created_at", -1).to_list(1000)
        result = []
        for draw in draws:
            try:
                # Ensure compatibility with older data formats
                draw_data = {
                    "id": str(draw["_id"]),
                    "draw_type": draw.get("draw_type", "Unknown"),
                    "start_time": draw.get("start_time", datetime.utcnow()),
                    "end_time": draw.get("end_time", datetime.utcnow() + timedelta(days=1)),
                    "total_pot": float(draw.get("total_pot", 0.0)),
                    "total_tickets": int(draw.get("total_tickets", 0)),
                    "status": draw.get("status", "active"),
                    "first_place_winner": None,
                    "consolation_winners": [],
                    "platform_earnings": float(draw.get("platform_earnings", 0.0)),
                    "created_at": draw.get("created_at", datetime.utcnow())
                }

                # Handle legacy winner data if present
                if "first_place_winner" in draw and isinstance(draw["first_place_winner"], dict):
                    draw_data["first_place_winner"] = draw["first_place_winner"].get("user_id")
                if "consolation_winners" in draw and isinstance(draw["consolation_winners"], list):
                    draw_data["consolation_winners"] = [
                        winner.get("user_id") if isinstance(winner, dict) else winner
                        for winner in draw["consolation_winners"]
                    ]

                ticket_count = await tickets_collection.count_documents({"draw_id": str(draw["_id"])})
                draw_data["total_tickets"] = ticket_count

                result.append(DrawResponse(**draw_data))
            except Exception as e:
                logger.warning(f"Skipping invalid draw {str(draw['_id'])}: {str(e)}")
                continue

        if not draws:
            logger.info("No draws found in the database")
            return []
        if not result:
            logger.warning("No valid draws found after processing")
            return []

        return result
    except Exception as e:
        logger.error(f"Error retrieving draws: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving draws: {str(e)}")


@router.get("/users/all", response_model=List[UserResponse])
async def list_all_users(
        current_user: dict = Depends(get_current_admin_user)
):
    """List all users (Admin only)"""
    users = await users_collection.find().to_list(1000)
    return [
        UserResponse(
            id=str(user["_id"]),
            name=user["name"],
            email=user["email"],
            role=user["role"],
            referral_code=user["referral_code"],
            wallet_balance=user.get("wallet_balance", 0.0),
            total_referrals=user.get("total_referrals", 0),
            created_at=user["created_at"]
        )
        for user in users
    ]