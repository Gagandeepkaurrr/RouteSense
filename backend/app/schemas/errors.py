from typing import Any

from pydantic import BaseModel


class APIError(BaseModel):
    code: str
    message: str
    details: Any | None = None
    request_id: str | None = None


class ErrorResponse(BaseModel):
    status: str = "error"
    error: APIError
