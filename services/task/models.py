from sqlmodel import SQLModel, Field
import time

class Task(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    prompt: str
    task_type: str = "text"
    status: str = "pending"
    result: str | None = None
    created_at: float = Field(default_factory=lambda: time.time())

