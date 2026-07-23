"""Phase 1 SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from windows_folder_sizes_diff.db.base import Base


class Scan(Base):
    __tablename__ = "scans"
    __table_args__ = (
        Index("ix_scans_status_started_at", "status", "started_at"),
        Index("ix_scans_normalized_target_started_at", "normalized_target_path", "started_at"),
        Index("ix_scans_target_config_completed", "normalized_target_path", "configuration_hash", "completed_at"),
        Index("ix_scans_status_completed", "status", "completed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    target_path: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_target_path: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    history_days: Mapped[int] = mapped_column(Integer, nullable=False)
    growth_threshold_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    folders_discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    folders_analyzed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    folders_matched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_examined: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    measurement_algorithm_version: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    hierarchy_algorithm_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    baseline_scan_id: Mapped[int | None] = mapped_column(ForeignKey("scans.id"), nullable=True)
    comparison_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")
    comparison_failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    direct_measurement_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")
    hierarchy_aggregation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    directory_observations: Mapped[list["DirectoryObservation"]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
    )
    warnings: Mapped[list["ScanWarningRecord"]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
    )
    volume_observation: Mapped[Optional["VolumeObservation"]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Directory(Base):
    __tablename__ = "directories"
    __table_args__ = (
        Index("ix_directories_normalized_path", "normalized_path"),
        Index("ix_directories_parent_directory_id", "parent_directory_id"),
        Index("ix_directories_depth", "depth"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    normalized_path: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    display_path: Mapped[str] = mapped_column(Text, nullable=False)
    parent_normalized_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_directory_id: Mapped[int | None] = mapped_column(ForeignKey("directories.id"), nullable=True)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_seen_scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id"), nullable=False)
    last_seen_scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    observations: Mapped[list["DirectoryObservation"]] = relationship(back_populates="directory")


class DirectoryObservation(Base):
    __tablename__ = "directory_observations"
    __table_args__ = (
        UniqueConstraint("scan_id", "directory_id", name="uq_directory_observations_scan_directory"),
        Index("ix_directory_observations_scan_directory", "scan_id", "directory_id"),
        Index("ix_directory_observations_directory_scan", "directory_id", "scan_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), nullable=False)
    directory_id: Mapped[int] = mapped_column(ForeignKey("directories.id"), nullable=False)
    matching_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    direct_file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched_file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    direct_logical_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inclusive_logical_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inclusive_file_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    direct_child_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    descendant_directory_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    measurement_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    hierarchy_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    files_examined: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    measurement_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    measurement_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    scan: Mapped[Scan] = relationship(back_populates="directory_observations")
    directory: Mapped[Directory] = relationship(back_populates="observations")


class ScanWarningRecord(Base):
    __tablename__ = "scan_warnings"
    __table_args__ = (Index("ix_scan_warnings_scan_id", "scan_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), nullable=False)
    directory_id: Mapped[int | None] = mapped_column(ForeignKey("directories.id"), nullable=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    error_type: Mapped[str] = mapped_column(String(128), nullable=False)
    error_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    scan: Mapped[Scan] = relationship(back_populates="warnings")


class VolumeObservation(Base):
    __tablename__ = "volume_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_id: Mapped[int] = mapped_column(
        ForeignKey("scans.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    root_path: Mapped[str] = mapped_column(Text, nullable=False)
    total_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    free_bytes_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    free_bytes_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    captured_before_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    captured_after_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    scan: Mapped[Scan] = relationship(back_populates="volume_observation")
