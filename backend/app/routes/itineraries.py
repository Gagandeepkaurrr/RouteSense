"""Authenticated versioned itinerary generation and saved-trip endpoints."""
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.routes.auth import get_current_user
from app.database.models import User
from app.schemas.intake import TripExtractionRequest, TripExtractionResponse
from app.schemas.errors import ErrorResponse
from app.schemas.itinerary import (
    GeneratedItineraryResponse,
    InsufficientPoolResponse,
    SavedTripListItem,
)
from app.services.itinerary_service import (
    delete_saved_itinerary,
    generate_and_save_itinerary,
    get_saved_itinerary,
    list_saved_itineraries,
)

router = APIRouter(prefix="/api/v1/itineraries", tags=["Itineraries"])


@router.post(
    "/generate",
    response_model=(
        GeneratedItineraryResponse
        | TripExtractionResponse
        | InsufficientPoolResponse
    ),
    summary="Generate and save a complete Delhi itinerary",
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        422: {"model": ErrorResponse, "description": "Invalid prompt or insufficient qualifying POIs"},
        500: {"model": ErrorResponse, "description": "Generation or persistence failure"},
    },
)
def generate_itinerary(
    request: TripExtractionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return generate_and_save_itinerary(db, current_user, request)


@router.get(
    "",
    response_model=list[SavedTripListItem],
    summary="List the authenticated user's saved itineraries",
    responses={401: {"model": ErrorResponse, "description": "Authentication required"}},
)
def get_itineraries(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    trips = list_saved_itineraries(db, current_user)
    return [
        {
            "trip_id": trip.id,
            "city": trip.destination,
            "start_date": trip.start_date,
            "number_of_days": trip.days,
            "budget_per_person_inr": trip.budget_per_person,
            "number_of_travellers": trip.number_of_travellers,
            "status": trip.status,
            "created_at": trip.created_at,
        }
        for trip in trips
    ]


@router.get(
    "/{trip_id}",
    response_model=GeneratedItineraryResponse,
    summary="Retrieve a saved itinerary snapshot",
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Itinerary not found or not owned by user"},
        409: {"model": ErrorResponse, "description": "Legacy trip has no snapshot"},
    },
)
def get_itinerary(
    trip_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    trip = get_saved_itinerary(db, current_user, trip_id)
    if not trip.itinerary_json:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=409,
            detail={
                "code": "ITINERARY_SNAPSHOT_UNAVAILABLE",
                "message": "This older saved trip does not contain a complete itinerary snapshot.",
            },
        )
    return GeneratedItineraryResponse.model_validate(trip.itinerary_json)


@router.delete(
    "/{trip_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a saved itinerary",
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Itinerary not found or not owned by user"},
    },
)
def remove_itinerary(
    trip_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    delete_saved_itinerary(db, current_user, trip_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
