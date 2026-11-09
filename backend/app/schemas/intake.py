from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field


class TripExtractionRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    number_of_travellers: int | None = Field(default=None, ge=1, le=20)


class ExtractedTripFields(BaseModel):
    city: Literal["Delhi"] = "Delhi"
    days: int | None = Field(default=None, ge=1, le=14)
    budget_per_person_inr: float = Field(gt=0)
    total_group_budget_inr: float = Field(gt=0)
    start_date: date
    preferences: list[str]
    number_of_travellers: int = Field(ge=1, le=20)
    start_time: str
    pace: Literal["relaxed", "normal", "packed"]
    defaulted_fields: list[str] = Field(default_factory=list)


class ClarificationQuestion(BaseModel):
    field: str
    question: str


class TripExtractionResponse(BaseModel):
    status: Literal["ready", "needs_clarification"]
    extracted: ExtractedTripFields
    missing_fields: list[str] = Field(default_factory=list)
    questions: list[ClarificationQuestion] = Field(default_factory=list)
