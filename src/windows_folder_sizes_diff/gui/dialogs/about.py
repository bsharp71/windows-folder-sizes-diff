"""About dialog."""

from __future__ import annotations

from windows_folder_sizes_diff.gui.dialogs._text import ReadOnlyTextDialog


class AboutDialog(ReadOnlyTextDialog):
    """Application identity and current measurement capability."""

    def __init__(
        self,
        master,
        *,
        application_name: str,
        version: str,
        python_requirement: str,
        schema_revision: str,
        measurement_mode: str,
        database_path: str | None = None,
    ) -> None:
        lines = [
            f"Application name: {application_name}",
            f"Application version: {version}",
            f"Python requirement: {python_requirement}",
            f"Database schema revision: {schema_revision}",
            f"Measurement mode: {measurement_mode}",
        ]
        if database_path:
            lines.append(f"Database path: {database_path}")
        super().__init__(
            master,
            title="About",
            text="\n".join(lines),
            width=640,
        )
