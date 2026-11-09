"""add saved itinerary snapshots and provider identity

Revision ID: c3a91b72e410
Revises: b7abf5589083
Create Date: 2026-10-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c3a91b72e410"
down_revision: Union[str, Sequence[str], None] = "b7abf5589083"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pois",
        sa.Column("source_provider", sa.String(length=30), server_default="curated", nullable=False),
    )
    op.add_column("pois", sa.Column("provider_id", sa.String(length=150), nullable=True))
    op.create_unique_constraint(
        "uq_pois_provider_identity", "pois", ["source_provider", "provider_id"]
    )

    op.add_column("trips", sa.Column("prompt", sa.Text(), nullable=True))
    op.add_column("trips", sa.Column("budget_per_person", sa.Float(), nullable=True))
    op.add_column(
        "trips",
        sa.Column("number_of_travellers", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "trips",
        sa.Column("pace", sa.String(length=20), server_default="normal", nullable=False),
    )
    op.add_column(
        "trips",
        sa.Column(
            "warnings_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "trips",
        sa.Column(
            "not_scheduled_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "trips",
        sa.Column(
            "itinerary_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )

    op.add_column(
        "itinerary_days",
        sa.Column("total_distance_km", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "itinerary_days",
        sa.Column("total_travel_minutes", sa.Integer(), server_default="0", nullable=False),
    )

    op.add_column("itinerary_stops", sa.Column("score", sa.Float(), nullable=True))
    op.add_column("itinerary_stops", sa.Column("base_score", sa.Float(), nullable=True))
    op.add_column("itinerary_stops", sa.Column("score_method", sa.String(length=60), nullable=True))
    op.add_column("itinerary_stops", sa.Column("source", sa.String(length=30), nullable=True))
    op.add_column(
        "itinerary_stops",
        sa.Column(
            "sources_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "itinerary_stops",
        sa.Column(
            "matched_preferences_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "itinerary_stops",
        sa.Column(
            "route_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("itinerary_stops", "route_json")
    op.drop_column("itinerary_stops", "matched_preferences_json")
    op.drop_column("itinerary_stops", "sources_json")
    op.drop_column("itinerary_stops", "source")
    op.drop_column("itinerary_stops", "score_method")
    op.drop_column("itinerary_stops", "base_score")
    op.drop_column("itinerary_stops", "score")

    op.drop_column("itinerary_days", "total_travel_minutes")
    op.drop_column("itinerary_days", "total_distance_km")

    op.drop_column("trips", "itinerary_json")
    op.drop_column("trips", "not_scheduled_json")
    op.drop_column("trips", "warnings_json")
    op.drop_column("trips", "pace")
    op.drop_column("trips", "number_of_travellers")
    op.drop_column("trips", "budget_per_person")
    op.drop_column("trips", "prompt")

    op.drop_constraint("uq_pois_provider_identity", "pois", type_="unique")
    op.drop_column("pois", "provider_id")
    op.drop_column("pois", "source_provider")
