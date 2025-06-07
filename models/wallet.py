from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from enum import Enum

class TransactionType(str, Enum):
    CREDIT = "credit"
    DEBIT = "debit"

class TransactionStatus(str, Enum):
    COMPLETED = "completed"
    PENDING = "pending"
    FAILED = "failed"

class Transaction(BaseModel):
    id: str
    user_id: str
    type: TransactionType
    amount: float
    description: str
    status: TransactionStatus
    date: datetime
    account_name: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None


class WalletTopup(BaseModel):
    amount: float

class WalletWithdraw(BaseModel):
    amount: float
    account_name: str
    bank_name: str
    account_number: str

class WalletResponse(BaseModel):
    balance: float

class WalletDetails(BaseModel):
    balance: float
    transactions: List[Transaction]