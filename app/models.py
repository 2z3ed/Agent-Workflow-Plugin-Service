from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatusEnum(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class TaskCreateRequest(BaseModel):
    chat_id: str | None = None


class TaskResponse(BaseModel):
    task_id: str
    status: TaskStatusEnum
    created_at: str
    completed_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
