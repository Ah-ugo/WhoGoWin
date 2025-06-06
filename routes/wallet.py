import fastapi
from fastapi import APIRouter, HTTPException, Depends, status
from typing import List
from datetime import datetime
import pytz
from bson import ObjectId
from pydantic import BaseModel
import aiohttp
import os
from dotenv import load_dotenv

from models.wallet import WalletTopup, WalletWithdraw, WalletResponse, WalletDetails, Transaction
from routes.auth import get_current_user, get_current_admin_user
from database import users_collection, transactions_collection
from services.wallet_service import WalletService
from services.notification_service import NotificationService

load_dotenv()
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_API_URL = "https://api.paystack.co"

router = APIRouter()
wallet_service = WalletService()

class WithdrawalAction(BaseModel):
    action: str  # "approve" or "reject"
    reason: str = None  # Required for rejection

class BalanceAdjustment(BaseModel):
    amount: float  # Positive for credit, negative for debit
    description: str

class PaystackInitializeResponse(BaseModel):
    authorization_url: str
    access_code: str
    reference: str

@router.get("/balance", response_model=WalletResponse)
async def get_wallet_balance(current_user: dict = Depends(get_current_user)):
    """Get current wallet balance"""
    return WalletResponse(balance=current_user.get("wallet_balance", 0.0))

@router.get("/details", response_model=WalletDetails)
async def get_wallet_details(current_user: dict = Depends(get_current_user)):
    """Get wallet balance and transaction history"""
    transactions = await transactions_collection.find(
        {"user_id": str(current_user["_id"])}
    ).sort("date", -1).limit(50).to_list(50)

    transaction_list = []
    for txn in transactions:
        transaction_list.append(Transaction(
            id=str(txn["_id"]),
            user_id=txn["user_id"],
            type=txn["type"],
            amount=txn["amount"],
            description=txn["description"],
            status=txn["status"],
            date=txn["date"]
        ))

    return WalletDetails(
        balance=current_user.get("wallet_balance", 0.0),
        transactions=transaction_list
    )

@router.post("/topup", response_model=PaystackInitializeResponse)
async def topup_wallet(
        topup_data: WalletTopup,
        current_user: dict = Depends(get_current_user)
):
    """Initialize Paystack payment for wallet top-up"""
    if topup_data.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    if topup_data.amount > 100000:
        raise HTTPException(status_code=400, detail="Maximum topup amount is ₦100,000")

    # Initialize Paystack transaction
    async with aiohttp.ClientSession() as session:
        headers = {
            "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "amount": int(topup_data.amount * 100),  # Paystack expects amount in kobo
            "email": current_user["email"],
            "reference": f"topup_{str(current_user['_id'])}_{int(datetime.now(pytz.UTC).timestamp())}",
            "callback_url": "https://whogowin.onrender.com/api/v1/wallet/verify-payment",  # Update with your frontend redirect URL
            "currency": "NGN"
        }
        async with session.post(
            f"{PAYSTACK_API_URL}/transaction/initialize",
            json=payload,
            headers=headers
        ) as response:
            if response.status != 200:
                raise HTTPException(status_code=500, detail="Failed to initialize payment")
            data = await response.json()
            if not data.get("status"):
                raise HTTPException(status_code=500, detail=data.get("message", "Payment initialization failed"))

            # Store pending transaction
            transaction_doc = {
                "user_id": str(current_user["_id"]),
                "type": "credit",
                "amount": topup_data.amount,
                "description": "Wallet top-up via Paystack",
                "status": "pending",
                "date": datetime.now(pytz.UTC),
                "paystack_reference": payload["reference"]
            }
            await transactions_collection.insert_one(transaction_doc)

            return PaystackInitializeResponse(
                authorization_url=data["data"]["authorization_url"],
                access_code=data["data"]["access_code"],
                reference=payload["reference"]
            )

# @router.get("/verify-payment", response_model=dict)
# async def verify_payment(reference: str):
#     """Verify Paystack payment and credit wallet"""
#     async with aiohttp.ClientSession() as session:
#         headers = {
#             "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
#             "Content-Type": "application/json"
#         }
#         async with session.get(
#             f"{PAYSTACK_API_URL}/transaction/verify/{reference}",
#             headers=headers
#         ) as response:
#             if response.status != 200:
#                 raise HTTPException(status_code=500, detail="Failed to verify payment")
#             data = await response.json()
#             if not data.get("status") or data["data"]["status"] != "success":
#                 raise HTTPException(status_code=400, detail="Payment verification failed")
#
#             # Check if transaction already processed
#             transaction = await transactions_collection.find_one({"paystack_reference": reference})
#             if not transaction:
#                 raise HTTPException(status_code=400, detail="Transaction not found")
#             if transaction["status"] == "completed":
#                 return {"message": "Payment already processed"}
#
#             # Credit wallet
#             await wallet_service.credit_wallet(
#                 transaction["user_id"],
#                 transaction["amount"],
#                 f"Wallet top-up via Paystack (Ref: {reference})"
#             )
#
#             # Update transaction status
#             await transactions_collection.update_one(
#                 {"paystack_reference": reference},
#                 {"$set": {"status": "completed", "updated_at": datetime.now(pytz.UTC)}}
#             )
#
#             return {
#                 "message": "Payment verified and wallet credited",
#                 "amount": transaction["amount"],
#                 "new_balance": await wallet_service.get_balance(transaction["user_id"])
#             }


from fastapi.responses import HTMLResponse
# from fastapi import APIRouter, HTTPException, Request
# import aiohttp
# from datetime import datetime
# import pytz
#
# router = APIRouter()

@router.get("/verify-payment", response_class=HTMLResponse)
async def verify_payment(reference: str):
    """Verify Paystack payment and credit wallet"""
    async with aiohttp.ClientSession() as session:
        headers = {
            "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json"
        }
        async with session.get(
            f"{PAYSTACK_API_URL}/transaction/verify/{reference}",
            headers=headers
        ) as response:
            if response.status != 200:
                raise HTTPException(status_code=500, detail="Failed to verify payment")
            data = await response.json()
            if not data.get("status") or data["data"]["status"] != "success":
                raise HTTPException(status_code=400, detail="Payment verification failed")

            # Check if transaction already processed
            transaction = await transactions_collection.find_one({"paystack_reference": reference})
            if not transaction:
                raise HTTPException(status_code=400, detail="Transaction not found")
            if transaction["status"] == "completed":
                html_content = f"""
                <!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Payment Already Processed</title>
                    <style>
                        body {{
                            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                            background-color: #f2f2f7;
                            margin: 0;
                            padding: 0;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                            min-height: 100vh;
                            color: #1d1d1f;
                        }}
                        .container {{
                            background-color: #ffffff;
                            border-radius: 16px;
                            padding: 24px;
                            max-width: 400px;
                            width: 90%;
                            text-align: center;
                            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
                        }}
                        .info-icon {{
                            font-size: 48px;
                            color: #007aff;
                            margin-bottom: 16px;
                        }}
                        .title {{
                            font-size: 24px;
                            font-weight: bold;
                            margin-bottom: 12px;
                        }}
                        .message {{
                            font-size: 16px;
                            color: #86868b;
                            margin-bottom: 20px;
                        }}
                        .return-button {{
                            background-color: #007aff;
                            color: #ffffff;
                            padding: 12px 24px;
                            border-radius: 8px;
                            text-decoration: none;
                            font-weight: 600;
                            font-size: 16px;
                            display: inline-block;
                            transition: background-color 0.2s;
                        }}
                        .return-button:hover {{
                            background-color: #0051cb;
                        }}
                        @media (max-width: 600px) {{
                            .container {{
                                margin: 20px;
                            }}
                        }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="info-icon">ℹ️</div>
                        <h1 class="title">Payment Already Processed</h1>
                        <p class="message">This payment has already been processed and credited to your wallet.</p>
                        <a href="whogowin://" class="return-button">Return to App</a>
                    </div>
                </body>
                </html>
                """
                return HTMLResponse(content=html_content, status_code=200)

            # Credit wallet
            await wallet_service.credit_wallet(
                transaction["user_id"],
                transaction["amount"],
                f"Wallet top-up via Paystack (Ref: {reference})"
            )

            # Update transaction status
            await transactions_collection.update_one(
                {"paystack_reference": reference},
                {"$set": {"status": "completed", "updated_at": datetime.now(pytz.UTC)}}
            )

            # Prepare response data
            response_data = {
                "message": "Payment verified and wallet credited",
                "amount": transaction["amount"],
                "new_balance": await wallet_service.get_balance(transaction["user_id"])
            }

            # Return HTML with dynamic data
            html_content = f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Payment Successful</title>
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                        background-color: #f2f2f7;
                        margin: 0;
                        padding: 0;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                        color: #1d1d1f;
                    }}
                    .container {{
                        background-color: #ffffff;
                        border-radius: 16px;
                        padding: 24px;
                        max-width: 400px;
                        width: 90%;
                        text-align: center;
                        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
                    }}
                    .success-icon {{
                        font-size: 48px;
                        color: #34c759;
                        margin-bottom: 16px;
                    }}
                    .title {{
                        font-size: 24px;
                        font-weight: bold;
                        margin-bottom: 12px;
                    }}
                    .message {{
                        font-size: 16px;
                        color: #86868b;
                        margin-bottom: 20px;
                    }}
                    .details {{
                        background-color: #f2f2f7;
                        border-radius: 8px;
                        padding: 16px;
                        margin-bottom: 20px;
                    }}
                    .details p {{
                        margin: 8px 0;
                        font-size: 16px;
                    }}
                    .details .amount {{
                        font-weight: bold;
                        color: #34c759;
                    }}
                    .details .balance {{
                        font-weight: bold;
                    }}
                    .return-button {{
                        background-color: #007aff;
                        color: #ffffff;
                        padding: 12px 24px;
                        border-radius: 8px;
                        text-decoration: none;
                        font-weight: 600;
                        font-size: 16px;
                        display: inline-block;
                        transition: background-color 0.2s;
                    }}
                    .return-button:hover {{
                        background-color: #0051cb;
                    }}
                    @media (max-width: 600px) {{
                        .container {{
                            margin: 20px;
                        }}
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="success-icon">✔️</div>
                    <h1 class="title">Payment Successful</h1>
                    <p class="message">{response_data["message"]}</p>
                    <div class="details">
                        <p>Amount Credited: <span class="amount">₦{response_data["amount"]:,}</span></p>
                        <p>New Balance: <span class="balance">₦{response_data["new_balance"]:,}</span></p>
                    </div>
                    <a href="whogowin://" class="return-button">Return to App</a>
                </div>
            </body>
            </html>
            """
            return HTMLResponse(content=html_content, status_code=200)

@router.post("/webhook")
async def paystack_webhook(request: fastapi.Request):
    """Handle Paystack webhook events"""
    payload = await request.json()
    if payload["event"] == "charge.success":
        reference = payload["data"]["reference"]
        transaction = await transactions_collection.find_one({"paystack_reference": reference})
        if transaction and transaction["status"] == "pending":
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
                async with session.get(
                    f"{PAYSTACK_API_URL}/transaction/verify/{reference}",
                    headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data["data"]["status"] == "success":
                            await wallet_service.credit_wallet(
                                transaction["user_id"],
                                transaction["amount"],
                                f"Wallet top-up via Paystack (Ref: {reference})"
                            )
                            await transactions_collection.update_one(
                                {"paystack_reference": reference},
                                {"$set": {"status": "completed", "updated_at": datetime.now(pytz.UTC)}}
                            )
    return {"status": "success"}

@router.post("/withdraw", response_model=dict)
async def withdraw_from_wallet(
        withdraw_data: WalletWithdraw,
        current_user: dict = Depends(get_current_user)
):
    """Request withdrawal from wallet"""
    if withdraw_data.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    if withdraw_data.amount < 100:
        raise HTTPException(status_code=400, detail="Minimum withdrawal amount is ₦100")

    current_balance = current_user.get("wallet_balance", 0.0)
    if withdraw_data.amount > current_balance:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    transaction_doc = {
        "user_id": str(current_user["_id"]),
        "type": "debit",
        "amount": withdraw_data.amount,
        "description": "Withdrawal request",
        "status": "pending",
        "date": datetime.now(pytz.UTC),
        "withdrawal_request": True
    }
    await transactions_collection.insert_one(transaction_doc)

    return {
        "message": "Withdrawal request submitted successfully",
        "amount": withdraw_data.amount,
        "status": "pending",
        "note": "Your withdrawal will be processed within 24 hours"
    }

@router.get("/transactions", response_model=List[Transaction])
async def get_transactions(current_user: dict = Depends(get_current_user)):
    """Get user's transaction history"""
    transactions = await transactions_collection.find(
        {"user_id": str(current_user["_id"])}
    ).sort("date", -1).limit(100).to_list(100)

    return [
        Transaction(
            id=str(txn["_id"]),
            user_id=txn["user_id"],
            type=txn["type"],
            amount=txn["amount"],
            description=txn["description"],
            status=txn["status"],
            date=txn["date"]
        )
        for txn in transactions
    ]

@router.get("/transactions/all", response_model=List[Transaction])
async def get_all_transactions(
        current_user: dict = Depends(get_current_admin_user)
):
    """Get all transactions in the system (Admin only)"""
    transactions = await transactions_collection.find().sort("date", -1).to_list(1000)
    return [
        Transaction(
            id=str(txn["_id"]),
            user_id=txn["user_id"],
            type=txn["type"],
            amount=txn["amount"],
            description=txn["description"],
            status=txn["status"],
            date=txn["date"]
        )
        for txn in transactions
    ]

@router.get("/transactions/user/{user_id}", response_model=List[Transaction])
async def get_user_transactions(
        user_id: str,
        current_user: dict = Depends(get_current_admin_user)
):
    """Get transaction history for a specific user (Admin only)"""
    try:
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        transactions = await transactions_collection.find(
            {"user_id": user_id}
        ).sort("date", -1).limit(100).to_list(100)

        return [
            Transaction(
                id=str(txn["_id"]),
                user_id=txn["user_id"],
                type=txn["type"],
                amount=txn["amount"],
                description=txn["description"],
                status=txn["status"],
                date=txn["date"]
            )
            for txn in transactions
        ]
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid user ID")

@router.get("/withdrawals/pending", response_model=List[Transaction])
async def get_pending_withdrawals(
        current_user: dict = Depends(get_current_admin_user)
):
    """Get all pending withdrawal requests (Admin only)"""
    transactions = await transactions_collection.find(
        {"withdrawal_request": True, "status": "pending"}
    ).sort("date", -1).to_list(1000)
    return [
        Transaction(
            id=str(txn["_id"]),
            user_id=txn["user_id"],
            type=txn["type"],
            amount=txn["amount"],
            description=txn["description"],
            status=txn["status"],
            date=txn["date"]
        )
        for txn in transactions
    ]

@router.post("/withdrawals/{transaction_id}/action", response_model=dict)
async def process_withdrawal(
        transaction_id: str,
        action_data: WithdrawalAction,
        current_user: dict = Depends(get_current_admin_user)
):
    """Approve or reject a withdrawal request (Admin only)"""
    try:
        if action_data.action not in ["approve", "reject"]:
            raise HTTPException(status_code=400, detail="Invalid action. Use 'approve' or 'reject'")
        if action_data.action == "reject" and not action_data.reason:
            raise HTTPException(status_code=400, detail="Reason required for rejection")

        if action_data.action == "approve":
            await wallet_service.approve_withdrawal(transaction_id, str(current_user["_id"]))
            return {"message": "Withdrawal approved successfully"}
        else:
            await wallet_service.reject_withdrawal(transaction_id, str(current_user["_id"]), action_data.reason)
            return {"message": "Withdrawal rejected successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid transaction ID")

@router.post("/adjust/{user_id}", response_model=dict)
async def adjust_user_balance(
        user_id: str,
        adjustment_data: BalanceAdjustment,
        current_user: dict = Depends(get_current_admin_user)
):
    """Manually adjust a user's wallet balance (Admin only)"""
    try:
        await wallet_service.adjust_balance(
            user_id,
            adjustment_data.amount,
            adjustment_data.description,
            str(current_user["_id"])
        )
        new_balance = await wallet_service.get_balance(user_id)
        return {
            "message": "Balance adjusted successfully",
            "new_balance": new_balance
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid user ID")