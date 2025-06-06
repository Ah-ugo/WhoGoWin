from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class TicketCreate(BaseModel):
    draw_id: str
    ticket_price: float

class TicketResponse(BaseModel):
    id: str
    user_id: str
    draw_id: str
    draw_type: str
    ticket_price: float
    purchase_date: datetime
    status: str
    is_winner: bool = False
    prize_amount: Optional[float] = None

class TicketUpdate(BaseModel):
    status: Optional[str] = None
    is_winner: Optional[bool] = None
    prize_amount: Optional[float] = None