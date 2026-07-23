"""phase 3 hierarchical folder sizing

Revision ID: 0003_phase_3
Revises: 0002_phase_2
Create Date: 2026-07-23 14:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_phase_3"
down_revision: Union[str, Sequence[str], None] = "0002_phase_2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- directories table (SQLite-compatible via raw SQL) ---
    op.execute("ALTER TABLE directories ADD COLUMN parent_directory_id INTEGER REFERENCES directories(id)")
    op.execute("ALTER TABLE directories ADD COLUMN depth INTEGER NOT NULL DEFAULT 0")
    op.create_index("ix_directories_parent_directory_id", "directories", ["parent_directory_id"])
    op.create_index("ix_directories_depth", "directories", ["depth"])

    # --- directory_observations table ---
    op.add_column("directory_observations", sa.Column("inclusive_logical_bytes", sa.Integer(), nullable=True))
    op.add_column("directory_observations", sa.Column("inclusive_file_count", sa.Integer(), nullable=True))
    op.add_column(
        "directory_observations",
        sa.Column("direct_child_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "directory_observations",
        sa.Column("descendant_directory_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "directory_observations",
        sa.Column("hierarchy_status", sa.String(length=32), nullable=False, server_default="unavailable"),
    )

    # --- scans table ---
    op.add_column(
        "scans",
        sa.Column("hierarchy_algorithm_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "scans",
        sa.Column("direct_measurement_status", sa.String(length=32), nullable=False, server_default="not_started"),
    )
    op.add_column(
        "scans",
        sa.Column("hierarchy_aggregation_status", sa.String(length=32), nullable=False, server_default="unavailable"),
    )

    op.execute(
        "UPDATE scans SET direct_measurement_status = 'completed' "
        "WHERE status IN ('completed', 'completed_with_warnings') "
        "AND measurement_algorithm_version = 2"
    )


def downgrade() -> None:
    # scans
    op.drop_column("scans", "hierarchy_aggregation_status")
    op.drop_column("scans", "direct_measurement_status")
    op.drop_column("scans", "hierarchy_algorithm_version")

    # directory_observations
    op.drop_column("directory_observations", "hierarchy_status")
    op.drop_column("directory_observations", "descendant_directory_count")
    op.drop_column("directory_observations", "direct_child_count")
    op.drop_column("directory_observations", "inclusive_file_count")
    op.drop_column("directory_observations", "inclusive_logical_bytes")

    # directories
    op.drop_index("ix_directories_depth", table_name="directories")
    op.drop_index("ix_directories_parent_directory_id", table_name="directories")
    # SQLite doesn't support DROP COLUMN easily; use batch for downgrade
    with op.batch_alter_table("directories") as batch_op:
        batch_op.drop_column("depth")
        batch_op.drop_column("parent_directory_id")
