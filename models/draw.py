# from pydantic import BaseModel
# from typing import List, Optional
# from datetime import datetime
# from enum import Enum
#
# class DrawType(str, Enum):
#     DAILY = "Daily"
#     WEEKLY = "Weekly"
#     MONTHLY = "Monthly"
#
# class DrawStatus(str, Enum):
#     ACTIVE = "active"
#     COMPLETED = "completed"
#     CANCELLED = "cancelled"
#
# class Winner(BaseModel):
#     user_id: str
#     name: str
#     prize_amount: float
#
# class DrawCreate(BaseModel):
#     draw_type: DrawType
#     end_time: datetime

# class DrawResponse(BaseModel):
#     id: str
#     draw_type: str
#     start_time: datetime
#     end_time: datetime
#     total_pot: float
#     total_tickets: int
#     status: str
#     first_place_winner: Optional[Winner] = None
#     consolation_winners: List[Winner] = []
#     platform_earnings: float = 0.0
#     created_at: datetime


# class DrawResponse(BaseModel):
#     id: str
#     draw_type: str
#     start_time: datetime
#     end_time: datetime
#     total_pot: float
#     total_tickets: int
#     status: str
#     first_place_winner: Optional[str] = None
#     consolation_winners: List[str] = []
#     platform_earnings: float
#     created_at: datetime


# class DrawUpdate(BaseModel):
#     status: Optional[DrawStatus] = None
#     end_time: Optional[datetime] = None

# class DrawUpdate(BaseModel):
#     draw_type: Optional[str] = None
#     end_time: Optional[datetime] = None
#     status: Optional[str] = None


from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from enum import Enum

class DrawType(str, Enum):
    DAILY = "Daily"
    WEEKLY = "Weekly"
    MONTHLY = "Monthly"

class DrawStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class Winner(BaseModel):
    user_id: str
    name: str
    prize_amount: float

class DrawCreate(BaseModel):
    draw_type: DrawType
    end_time: datetime


class DrawResponse(BaseModel):
    id: str
    draw_type: str
    start_time: datetime
    end_time: datetime
    total_pot: float
    total_tickets: int
    status: str
    winning_numbers: List[int] = []
    first_place_winner: Optional[Winner] = None
    consolation_winners: List[Winner] = []
    platform_earnings: float
    created_at: datetime

class DrawUpdate(BaseModel):
    draw_type: Optional[str] = None
    end_time: Optional[datetime] = None
    status: Optional[str] = None