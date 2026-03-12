from sqlmodel import SQLModel, Field
from typing import Optional

class Task(SQLModel, table=True):
    id: int = Field(primary_key=True)
    prompt: str
    task_type: str
    status: str
    result: Optional[str] = None
    validator_result: Optional[str] = None
    worker_id: Optional[int] = None
    validator_worker_id: Optional[int] = None
    created_at: float
    updated_at: float

class Worker(SQLModel, table=True):
    id: int = Field(primary_key=True)
    name: str
    power: int
    reputation: float
    balance: float
    status: str
    last_seen: float

class Transaction(SQLModel, table=True):
    id: Optional[int] = Field(primary_key=True)
    worker_id: int
    amount: float
    description: str
    timestamp: str

