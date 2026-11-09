"""Versioned trip-intake endpoint for prompt extraction and clarification."""
from fastapi import APIRouter

from app.schemas.intake import TripExtractionRequest, TripExtractionResponse
from app.schemas.errors import ErrorResponse
from app.services.intake_service import extract_trip_prompt

router = APIRouter(prefix="/api/v1/itineraries", tags=["Itineraries"])


@router.post(
    "/extract",
    response_model=TripExtractionResponse,
    summary="Extract trip details from a free-text prompt",
    responses={422: {"model": ErrorResponse, "description": "Unsupported destination or invalid trip details"}},
)
def extract_itinerary_request(
    request: TripExtractionRequest,
) -> TripExtractionResponse:
    """Extract and validate prompt fields without generating an itinerary."""
    return extract_trip_prompt(request)
