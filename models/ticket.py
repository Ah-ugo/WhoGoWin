from pydantic import BaseModel, validator
from typing import Optional, List
from datetime import datetime

class TicketCreate(BaseModel):
    draw_id: str
    ticket_price: float
    selected_numbers: List[int]

    @validator('selected_numbers')
    def validate_numbers(cls, v):
        if len(v) != 5:
            raise ValueError("Exactly 5 numbers must be selected")
        if not all(1 <= num <= 30 for num in v):
            raise ValueError("Numbers must be between 1 and 30")
        if len(v) != len(set(v)):
            raise ValueError("Numbers must be unique")
        return sorted(v)

class TicketResponse(BaseModel):
    id: str
    user_id: str
    draw_id: str
    draw_type: str
    ticket_price: float
    selected_numbers: List[int]
    match_count: Optional[int] = None
    purchase_date: datetime
    status: str
    is_winner: bool = False
    prize_amount: Optional[float] = None

class TicketUpdate(BaseModel):
    status: Optional[str] = None
    is_winner: Optional[bool] = None
    prize_amount: Optional[float] = None