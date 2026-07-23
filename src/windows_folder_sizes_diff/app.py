"""Application entry point."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from windows_folder_sizes_diff.config import load_settings
from windows_folder_sizes_diff.constants import APPLICATION_LOG_PATH, LOGS_DIR
from windows_folder_sizes_diff.db.engine import create_database_engine, create_session_factory
from windows_folder_sizes_diff.db.lifecycle import ScanLifecycleService
from windows_folder_sizes_diff.db.schema import assert_schema_current
from windows_folder_sizes_diff.gui.main_window import MainWindow


def configure_logging() -> None:
    """Configure diagnostic logging separate from scan result reports."""

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            RotatingFileHandler(
                APPLICATION_LOG_PATH,
                maxBytes=1_000_000,
                backupCount=3,
                encoding="utf-8",
            )
        ],
    )


def main() -> None:
    configure_logging()
    logging.getLogger(__name__).info("Application startup")
    settings = load_settings()
    engine = create_database_engine(settings.database_path)
    assert_schema_current(engine, settings.database_path)
    session_factory = create_session_factory(engine)
    lifecycle_service = ScanLifecycleService(session_factory)
    recovered = lifecycle_service.recover_stale_scans()
    if recovered:
        logging.getLogger(__name__).warning("Recovered %s stale scan(s)", recovered)
    window = MainWindow(
        settings=settings,
        session_factory=session_factory,
        lifecycle_service=lifecycle_service,
    )
    window.run()


if __name__ == "__main__":
    main()
