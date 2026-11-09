"""Shared prompt extraction and validation for versioned itinerary APIs."""
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.schemas.intake import (
    ClarificationQuestion,
    ExtractedTripFields,
    TripExtractionRequest,
    TripExtractionResponse,
)
from app.services.planner.parser import parse_prompt

DELHI_TZ = ZoneInfo("Asia/Kolkata")
DEFAULT_BUDGET_PER_PERSON_INR = 3000.0

CLARIFICATION_QUESTIONS = {
    "days": "How many days would you like to spend exploring Delhi?",
    "preferences": "What kinds of places would you like to visit (for example, monuments, food, cafes or parks)?",
}


def extract_trip_prompt(request: TripExtractionRequest) -> TripExtractionResponse:
    today = datetime.now(DELHI_TZ).date()
    parsed = parse_prompt(request.prompt, today=today)

    if parsed.city != "delhi":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "UNSUPPORTED_CITY",
                "message": "RouteSense currently supports Delhi only.",
                "requested_city": parsed.city,
                "supported_city": "Delhi",
            },
        )

    if "invalid_date" in parsed.missing:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_DATE",
                "message": "The date in the prompt is not a valid calendar date.",
            },
        )

    if parsed.days is not None and not 1 <= parsed.days <= 14:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_DAYS",
                "message": "Trip duration must be between 1 and 14 days.",
                "provided_days": parsed.days,
            },
        )

    start_date = parsed.start_date or today
    if start_date < today:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_DATE",
                "message": "Trip start date cannot be in the past.",
            },
        )

    budget = parsed.budget_total_inr
    defaulted_fields: list[str] = []
    if budget is None:
        budget = DEFAULT_BUDGET_PER_PERSON_INR
        defaulted_fields.append("budget_per_person_inr")
    if parsed.start_date is None:
        defaulted_fields.append("start_date")
    if request.number_of_travellers is None and parsed.travellers == 1:
        defaulted_fields.append("number_of_travellers")

    travellers = request.number_of_travellers or parsed.travellers
    if budget <= 0 or budget > 1_000_000:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_BUDGET",
                "message": "Per-person trip budget must be greater than 0 and no more than INR 1,000,000.",
            },
        )

    missing_fields = [
        field for field in ("days", "preferences")
        if field in parsed.missing
    ]
    questions = [
        ClarificationQuestion(field=field, question=CLARIFICATION_QUESTIONS[field])
        for field in missing_fields
    ]

    extracted = ExtractedTripFields(
        city="Delhi",
        days=parsed.days,
        budget_per_person_inr=budget,
        total_group_budget_inr=budget * travellers,
        start_date=start_date,
        preferences=parsed.interests,
        number_of_travellers=travellers,
        start_time=parsed.start_time or "09:00",
        pace=parsed.pace,
        defaulted_fields=defaulted_fields,
    )

    return TripExtractionResponse(
        status="needs_clarification" if missing_fields else "ready",
        extracted=extracted,
        missing_fields=missing_fields,
        questions=questions,
    )
