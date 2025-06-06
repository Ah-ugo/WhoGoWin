from fastapi import APIRouter, HTTPException, Depends, status
from typing import List
from bson import ObjectId
import secrets
import string
from datetime import datetime

from models.user import UserResponse, UserUpdate, Role
from routes.auth import get_current_user, get_current_admin_user
from database import users_collection
from services.notification_service import NotificationService

router = APIRouter()
notification_service = NotificationService()


def generate_referral_code():
    """Generate a unique referral code"""
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(current_user: dict = Depends(get_current_user)):
    """Get current user's profile"""
    return UserResponse(
        id=str(current_user["_id"]),
        name=current_user["name"],
        email=current_user["email"],
        role=current_user["role"],
        referral_code=current_user["referral_code"],
        wallet_balance=current_user.get("wallet_balance", 0.0),
        total_referrals=current_user.get("total_referrals", 0),
        created_at=current_user["created_at"]
    )


@router.put("/profile", response_model=UserResponse)
async def update_profile(
        user_update: UserUpdate,
        current_user: dict = Depends(get_current_user)
):
    """Update current user's profile (name for all users, email/role for admins only)"""
    update_data = {}
    is_admin = current_user["role"] == Role.ADMIN

    if user_update.name:
        update_data["name"] = user_update.name

    if user_update.email:
        if not is_admin:
            raise HTTPException(status_code=403, detail="Only admins can update email")
        existing_user = await users_collection.find_one({
            "email": user_update.email,
            "_id": {"$ne": current_user["_id"]}
        })
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already taken")
        update_data["email"] = user_update.email

    if user_update.role:
        if not is_admin:
            raise HTTPException(status_code=403, detail="Only admins can update role")
        update_data["role"] = user_update.role

    if not update_data:
        raise HTTPException(status_code=400, detail="No updates provided")

    await users_collection.update_one(
        {"_id": current_user["_id"]},
        {"$set": update_data}
    )

    updated_user = await users_collection.find_one({"_id": current_user["_id"]})
    return UserResponse(
        id=str(updated_user["_id"]),
        name=updated_user["name"],
        email=updated_user["email"],
        role=updated_user["role"],
        referral_code=updated_user["referral_code"],
        wallet_balance=updated_user.get("wallet_balance", 0.0),
        total_referrals=updated_user.get("total_referrals", 0),
        created_at=updated_user["created_at"]
    )


@router.get("/all", response_model=List[UserResponse])
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


@router.get("/{user_id}", response_model=UserResponse)
async def get_user_profile(
        user_id: str,
        current_user: dict = Depends(get_current_admin_user)
):
    """Get a specific user's profile (Admin only)"""
    try:
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return UserResponse(
            id=str(user["_id"]),
            name=user["name"],
            email=user["email"],
            role=user["role"],
            referral_code=user["referral_code"],
            wallet_balance=user.get("wallet_balance", 0.0),
            total_referrals=user.get("total_referrals", 0),
            created_at=user["created_at"]
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid user ID")


@router.put("/{user_id}/update", response_model=UserResponse)
async def update_user_profile(
        user_id: str,
        user_update: UserUpdate,
        current_user: dict = Depends(get_current_admin_user)
):
    """Update any user's profile (Admin only)"""
    try:
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        update_data = {}
        if user_update.name:
            update_data["name"] = user_update.name
        if user_update.email:
            existing_user = await users_collection.find_one({
                "email": user_update.email,
                "_id": {"$ne": ObjectId(user_id)}
            })
            if existing_user:
                raise HTTPException(status_code=400, detail="Email already taken")
            update_data["email"] = user_update.email
        if user_update.role:
            update_data["role"] = user_update.role

        if not update_data:
            raise HTTPException(status_code=400, detail="No updates provided")

        await users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": update_data}
        )

        updated_user = await users_collection.find_one({"_id": ObjectId(user_id)})

        # Notify user of profile update
        if updated_user.get("push_token"):
            await notification_service.send_push_notification(
                updated_user["push_token"],
                "Profile Updated",
                "Your profile has been updated by an administrator."
            )
        await notification_service.save_notification(
            user_id=str(updated_user["_id"]),
            title="Profile Updated",
            body="Your profile has been updated by an administrator.",
            notification_type="profile_update"
        )

        return UserResponse(
            id=str(updated_user["_id"]),
            name=updated_user["name"],
            email=updated_user["email"],
            role=updated_user["role"],
            referral_code=updated_user["referral_code"],
            wallet_balance=updated_user.get("wallet_balance", 0.0),
            total_referrals=updated_user.get("total_referrals", 0),
            created_at=updated_user["created_at"]
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid user ID or update data")


@router.post("/{user_id}/toggle-active", response_model=dict)
async def toggle_user_active(
        user_id: str,
        current_user: dict = Depends(get_current_admin_user)
):
    """Deactivate or reactivate a user account (Admin only)"""
    try:
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if str(user["_id"]) == str(current_user["_id"]):
            raise HTTPException(status_code=400, detail="Cannot deactivate own account")

        new_status = not user.get("is_active", True)
        await users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"is_active": new_status}}
        )

        # Notify user of account status change
        if user.get("push_token"):
            status_text = "deactivated" if not new_status else "reactivated"
            await notification_service.send_push_notification(
                user["push_token"],
                f"Account {status_text.capitalize()}",
                f"Your account has been {status_text} by an administrator."
            )
        await notification_service.save_notification(
            user_id=user_id,
            title=f"Account {status_text.capitalize()}",
            body=f"Your account has been {status_text} by an administrator.",
            notification_type="account_status"
        )

        return {"message": f"User account {'deactivated' if not new_status else 'reactivated'}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid user ID")


@router.post("/{user_id}/reset-referral", response_model=dict)
async def reset_referral_code(
        user_id: str,
        current_user: dict = Depends(get_current_admin_user)
):
    """Reset a user's referral code (Admin only)"""
    try:
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Generate new unique referral code
        new_referral_code = generate_referral_code()
        while await users_collection.find_one({"referral_code": new_referral_code}):
            new_referral_code = generate_referral_code()

        await users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"referral_code": new_referral_code}}
        )

        # Notify user of referral code reset
        if user.get("push_token"):
            await notification_service.send_push_notification(
                user["push_token"],
                "Referral Code Reset",
                f"Your referral code has been reset to {new_referral_code}."
            )
        await notification_service.save_notification(
            user_id=user_id,
            title="Referral Code Reset",
            body=f"Your referral code has been reset to {new_referral_code}.",
            notification_type="referral_reset"
        )

        return {"message": "Referral code reset successfully", "new_referral_code": new_referral_code}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid user ID")