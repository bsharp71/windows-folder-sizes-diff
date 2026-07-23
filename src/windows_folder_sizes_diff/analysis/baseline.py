"""Baseline scan selection."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from windows_folder_sizes_diff.analysis.models import BaselineSelection
from windows_folder_sizes_diff.db.configuration import MEASUREMENT_ALGORITHM_VERSION
from windows_folder_sizes_diff.db.models import Scan


class BaselineSelector:
    """Find the previous comparable Phase 2 scan."""

    def find_previous_comparable_scan(
        self,
        session: Session,
        current_scan_id: int,
    ) -> BaselineSelection:
        current = session.get(Scan, current_scan_id)
        if current is None:
            return BaselineSelection(
                current_scan_id=current_scan_id,
                baseline_scan_id=None,
                status="not_comparable",
                reason="Current scan was not found.",
            )
        if current.measurement_algorithm_version != MEASUREMENT_ALGORITHM_VERSION:
            return BaselineSelection(
                current_scan_id=current_scan_id,
                baseline_scan_id=None,
                status="not_comparable",
                reason="Current scan is not a Phase 2 measurement scan.",
            )
        if current.completed_at is None:
            return BaselineSelection(
                current_scan_id=current_scan_id,
                baseline_scan_id=None,
                status="not_comparable",
                reason="Current scan is not complete.",
            )

        statement = (
            select(Scan)
            .where(
                Scan.id != current.id,
                Scan.status == "completed",
                Scan.measurement_algorithm_version == MEASUREMENT_ALGORITHM_VERSION,
                Scan.normalized_target_path == current.normalized_target_path,
                Scan.configuration_hash == current.configuration_hash,
                Scan.completed_at < current.completed_at,
            )
            .order_by(Scan.completed_at.desc())
            .limit(1)
        )
        baseline = session.scalar(statement)
        if baseline is None:
            return BaselineSelection(
                current_scan_id=current_scan_id,
                baseline_scan_id=None,
                status="baseline_created",
                reason="No previous comparable completed scan exists.",
            )
        return BaselineSelection(
            current_scan_id=current_scan_id,
            baseline_scan_id=baseline.id,
            status="selected",
            reason="Previous comparable completed scan selected.",
        )
