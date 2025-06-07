from datetime import datetime
import pytz
from bson import ObjectId
from database import users_collection, transactions_collection
from services.notification_service import NotificationService

class WalletService:
    def __init__(self):
        self.notification_service = NotificationService()

    async def credit_wallet(self, user_id: str, amount: float, description: str):
        """Credit amount to user's wallet"""
        if amount <= 0:
            raise ValueError("Amount must be positive")

        # Atomically update user balance and create transaction
        user = await users_collection.find_one_and_update(
            {"_id": ObjectId(user_id)},
            {"$inc": {"wallet_balance": amount}},
            return_document=True
        )
        if not user:
            raise ValueError("User not found")

        transaction_doc = {
            "user_id": user_id,
            "type": "credit",
            "amount": amount,
            "description": description,
            "status": "completed",
            "date": datetime.now(pytz.UTC)
        }
        await transactions_collection.insert_one(transaction_doc)

        # Notify user
        if user.get("push_token"):
            await self.notification_service.send_push_notification(
                user["push_token"],
                "Wallet Credited",
                f"Your wallet has been credited with ₦{amount:,.0f}. Reason: {description}"
            )
        await self.notification_service.save_notification(
            user_id=user_id,
            title="Wallet Credited",
            body=f"Your wallet has been credited with ₦{amount:,.0f}. Reason: {description}",
            notification_type="wallet_credit"
        )

    async def debit_wallet(self, user_id: str, amount: float, description: str):
        """Debit amount from user's wallet"""
        if amount <= 0:
            raise ValueError("Amount must be positive")

        # Atomically check balance and debit
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise ValueError("User not found")
        if user.get("wallet_balance", 0.0) < amount:
            raise ValueError("Insufficient wallet balance")

        updated_user = await users_collection.find_one_and_update(
            {"_id": ObjectId(user_id), "wallet_balance": {"$gte": amount}},
            {"$inc": {"wallet_balance": -amount}},
            return_document=True
        )
        if not updated_user:
            raise ValueError("Insufficient wallet balance or user not found")

        transaction_doc = {
            "user_id": user_id,
            "type": "debit",
            "amount": amount,
            "description": description,
            "status": "completed",
            "date": datetime.now(pytz.UTC)
        }
        await transactions_collection.insert_one(transaction_doc)

        # Notify user
        if user.get("push_token"):
            await self.notification_service.send_push_notification(
                user["push_token"],
                "Wallet Debited",
                f"Your wallet has been debited with ₦{amount:,.0f}. Reason: {description}"
            )
        await self.notification_service.save_notification(
            user_id=user_id,
            title="Wallet Debited",
            body=f"Your wallet has been debited with ₦{amount:,.0f}. Reason: {description}",
            notification_type="wallet_debit"
        )

    async def get_balance(self, user_id: str) -> float:
        """Get user's current wallet balance"""
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
        return user.get("wallet_balance", 0.0) if user else 0.0

    async def approve_withdrawal(self, transaction_id: str, admin_id: str):
        """Approve a pending withdrawal request"""
        transaction = await transactions_collection.find_one({"_id": ObjectId(transaction_id)})
        if not transaction or transaction["status"] != "pending" or not transaction.get("withdrawal_request"):
            raise ValueError("Invalid or non-pending withdrawal request")

        user = await users_collection.find_one({"_id": ObjectId(transaction["user_id"])})
        if not user or user.get("wallet_balance", 0.0) < transaction["amount"]:
            raise ValueError("User not found or insufficient balance")

        # Atomically debit wallet and update transaction
        updated_user = await users_collection.find_one_and_update(
            {"_id": ObjectId(transaction["user_id"]), "wallet_balance": {"$gte": transaction["amount"]}},
            {"$inc": {"wallet_balance": -transaction["amount"]}},
            return_document=True
        )
        if not updated_user:
            raise ValueError("Insufficient balance or user not found")

        await transactions_collection.update_one(
            {"_id": ObjectId(transaction_id)},
            {
                "$set": {
                    "status": "completed",
                    "approved_by": admin_id,
                    "approved_at": datetime.now(pytz.UTC)
                }
            }
        )

        # Notify user with bank details
        if user.get("push_token"):
            await self.notification_service.send_push_notification(
                user["push_token"],
                "Withdrawal Approved",
                f"Your withdrawal of ₦{transaction['amount']:,.0f} to {transaction.get('account_name')} ({transaction.get('bank_name')}, {transaction.get('account_number')}) has been approved."
            )
        await self.notification_service.save_notification(
            user_id=transaction["user_id"],
            title="Withdrawal Approved",
            body=f"Your withdrawal of ₦{transaction['amount']:,.0f} to {transaction.get('account_name')} ({transaction.get('bank_name')}, {transaction.get('account_number')}) has been approved.",
            notification_type="withdrawal_approved"
        )

    async def reject_withdrawal(self, transaction_id: str, admin_id: str, reason: str):
        """Reject a pending withdrawal request"""
        transaction = await transactions_collection.find_one({"_id": ObjectId(transaction_id)})
        if not transaction or transaction["status"] != "pending" or not transaction.get("withdrawal_request"):
            raise ValueError("Invalid or non-pending withdrawal request")

        await transactions_collection.update_one(
            {"_id": ObjectId(transaction_id)},
            {
                "$set": {
                    "status": "failed",
                    "rejected_by": admin_id,
                    "rejected_at": datetime.now(pytz.UTC),
                    "rejection_reason": reason
                }
            }
        )

        user = await users_collection.find_one({"_id": ObjectId(transaction["user_id"])})
        if user and user.get("push_token"):
            await self.notification_service.send_push_notification(
                user["push_token"],
                "Withdrawal Rejected",
                f"Your withdrawal request of ₦{transaction['amount']:,.0f} was rejected. Reason: {reason}"
            )
        if user:
            await self.notification_service.save_notification(
                user_id=transaction["user_id"],
                title="Withdrawal Rejected",
                body=f"Your withdrawal request of ₦{transaction['amount']:,.0f} was rejected. Reason: {reason}",
                notification_type="withdrawal_rejected"
            )

    async def adjust_balance(self, user_id: str, amount: float, description: str, admin_id: str):
        """Manually adjust user's wallet balance (positive for credit, negative for debit)"""
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise ValueError("User not found")
        if amount == 0:
            raise ValueError("Adjustment amount cannot be zero")
        if amount < 0 and user.get("wallet_balance", 0.0) < abs(amount):
            raise ValueError("Insufficient wallet balance for debit adjustment")

        # Atomically update balance
        await users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$inc": {"wallet_balance": amount}}
        )

        # Create transaction record
        transaction_doc = {
            "user_id": user_id,
            "type": "credit" if amount > 0 else "debit",
            "amount": abs(amount),
            "description": f"Admin adjustment: {description}",
            "status": "completed",
            "date": datetime.now(pytz.UTC),
            "adjusted_by": admin_id
        }
        await transactions_collection.insert_one(transaction_doc)

        # Notify user
        action = "credited" if amount > 0 else "debited"
        if user.get("push_token"):
            await self.notification_service.send_push_notification(
                user["push_token"],
                "Wallet Balance Adjusted",
                f"Your wallet has been {action} with ₦{abs(amount):,.0f}. Reason: {description}"
            )
        await self.notification_service.save_notification(
            user_id=user_id,
            title="Wallet Balance Adjusted",
            body=f"Your wallet has been {action} with ₦{abs(amount):,.0f}. Reason: {description}",
            notification_type="wallet_adjustment"
        )