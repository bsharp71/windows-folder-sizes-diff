"""phase 2 snapshot differences

Revision ID: 0002_phase_2
Revises: 0001_phase_1
Create Date: 2026-07-23 13:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_phase_2"
down_revision: Union[str, Sequence[str], None] = "0001_phase_1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("directory_observations", sa.Column("direct_logical_bytes", sa.Integer(), nullable=True))
    op.add_column(
        "directory_observations",
        sa.Column("measurement_status", sa.String(length=32), nullable=False, server_default="pending"),
    )
    op.add_column(
        "directory_observations",
        sa.Column("files_examined", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("directory_observations", sa.Column("measurement_started_at", sa.DateTime(), nullable=True))
    op.add_column("directory_observations", sa.Column("measurement_completed_at", sa.DateTime(), nullable=True))

    op.add_column(
        "scans",
        sa.Column("measurement_algorithm_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("scans", sa.Column("baseline_scan_id", sa.Integer(), nullable=True))
    op.add_column(
        "scans",
        sa.Column("comparison_status", sa.String(length=32), nullable=False, server_default="not_started"),
    )
    op.add_column("scans", sa.Column("comparison_failure_message", sa.Text(), nullable=True))
    op.create_index(
        "ix_scans_target_config_completed",
        "scans",
        ["normalized_target_path", "configuration_hash", "completed_at"],
    )
    op.create_index("ix_scans_status_completed", "scans", ["status", "completed_at"])


def downgrade() -> None:
    op.drop_index("ix_scans_status_completed", table_name="scans")
    op.drop_index("ix_scans_target_config_completed", table_name="scans")
    op.drop_column("scans", "comparison_failure_message")
    op.drop_column("scans", "comparison_status")
    op.drop_column("scans", "baseline_scan_id")
    op.drop_column("scans", "measurement_algorithm_version")
    op.drop_column("directory_observations", "measurement_completed_at")
    op.drop_column("directory_observations", "measurement_started_at")
    op.drop_column("directory_observations", "files_examined")
    op.drop_column("directory_observations", "measurement_status")
    op.drop_column("directory_observations", "direct_logical_bytes")
