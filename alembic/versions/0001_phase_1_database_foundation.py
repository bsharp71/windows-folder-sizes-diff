"""phase 1 database foundation

Revision ID: 0001_phase_1
Revises:
Create Date: 2026-07-23 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_phase_1"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scan_uuid", sa.String(length=36), nullable=False),
        sa.Column("target_path", sa.Text(), nullable=False),
        sa.Column("normalized_target_path", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("history_days", sa.Integer(), nullable=False),
        sa.Column("growth_threshold_mb", sa.Integer(), nullable=False),
        sa.Column("configuration_hash", sa.String(length=64), nullable=False),
        sa.Column("folders_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("folders_analyzed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("folders_matched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("files_examined", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("scan_uuid", name="uq_scans_scan_uuid"),
    )
    op.create_index("ix_scans_status_started_at", "scans", ["status", "started_at"])
    op.create_index(
        "ix_scans_normalized_target_started_at",
        "scans",
        ["normalized_target_path", "started_at"],
    )

    op.create_table(
        "directories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("normalized_path", sa.Text(), nullable=False),
        sa.Column("display_path", sa.Text(), nullable=False),
        sa.Column("parent_normalized_path", sa.Text(), nullable=True),
        sa.Column("first_seen_scan_id", sa.Integer(), sa.ForeignKey("scans.id"), nullable=False),
        sa.Column("last_seen_scan_id", sa.Integer(), sa.ForeignKey("scans.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("normalized_path", name="uq_directories_normalized_path"),
    )
    op.create_index("ix_directories_normalized_path", "directories", ["normalized_path"])

    op.create_table(
        "directory_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scan_id", sa.Integer(), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("directory_id", sa.Integer(), sa.ForeignKey("directories.id"), nullable=False),
        sa.Column("matching_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("direct_file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint(
            "scan_id",
            "directory_id",
            name="uq_directory_observations_scan_directory",
        ),
    )
    op.create_index(
        "ix_directory_observations_scan_directory",
        "directory_observations",
        ["scan_id", "directory_id"],
    )
    op.create_index(
        "ix_directory_observations_directory_scan",
        "directory_observations",
        ["directory_id", "scan_id"],
    )

    op.create_table(
        "scan_warnings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scan_id", sa.Integer(), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("directory_id", sa.Integer(), sa.ForeignKey("directories.id"), nullable=True),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("error_type", sa.String(length=128), nullable=False),
        sa.Column("error_code", sa.Integer(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_scan_warnings_scan_id", "scan_warnings", ["scan_id"])

    op.create_table(
        "volume_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scan_id", sa.Integer(), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("root_path", sa.Text(), nullable=False),
        sa.Column("total_bytes", sa.Integer(), nullable=True),
        sa.Column("free_bytes_before", sa.Integer(), nullable=True),
        sa.Column("free_bytes_after", sa.Integer(), nullable=True),
        sa.Column("captured_before_at", sa.DateTime(), nullable=True),
        sa.Column("captured_after_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.UniqueConstraint("scan_id", name="uq_volume_observations_scan_id"),
    )


def downgrade() -> None:
    op.drop_table("volume_observations")
    op.drop_index("ix_scan_warnings_scan_id", table_name="scan_warnings")
    op.drop_table("scan_warnings")
    op.drop_index("ix_directory_observations_directory_scan", table_name="directory_observations")
    op.drop_index("ix_directory_observations_scan_directory", table_name="directory_observations")
    op.drop_table("directory_observations")
    op.drop_index("ix_directories_normalized_path", table_name="directories")
    op.drop_table("directories")
    op.drop_index("ix_scans_normalized_target_started_at", table_name="scans")
    op.drop_index("ix_scans_status_started_at", table_name="scans")
    op.drop_table("scans")
