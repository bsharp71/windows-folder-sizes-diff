"""Configuration loading and saving."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from windows_folder_sizes_diff.constants import CONFIG_PATH, DEFAULT_DATABASE_PATH


class AppSettings(BaseModel):
    """Validated application settings compatible with the existing config.yaml."""

    model_config = ConfigDict(populate_by_name=True)

    target_directory: Path = Field(default=Path("C:/"), alias="TargetDirectory")
    growth_threshold_mb: int = Field(default=100, ge=0, alias="GrowthThresholdMB")
    history_days: int = Field(default=1, ge=1, alias="HistoryDays")
    database_path: Path = Field(default=DEFAULT_DATABASE_PATH, alias="DatabasePath")

    @field_validator("target_directory", "database_path", mode="before")
    @classmethod
    def normalize_path_setting(cls, value: str | Path) -> Path:
        return Path(value).expanduser()


def _parse_scalar(value: str) -> str:
    stripped = value.strip()
    if (
        len(stripped) >= 2
        and stripped[0] == stripped[-1]
        and stripped[0] in {"'", '"'}
    ):
        return stripped[1:-1]
    return stripped


def _read_simple_yaml(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise ValueError(f"Invalid config line {line_number}: expected 'Key: Value'.")
        key, _, value = stripped.partition(":")
        values[key.strip()] = _parse_scalar(value)
    return values


def load_settings(path: Path = CONFIG_PATH) -> AppSettings:
    """Load settings from config.yaml, returning defaults when the file is missing."""

    if not path.exists():
        return AppSettings()

    try:
        return AppSettings.model_validate(_read_simple_yaml(path))
    except ValidationError as exc:
        raise ValueError(f"Invalid settings in {path}: {exc}") from exc


def save_settings(settings: AppSettings, path: Path = CONFIG_PATH) -> None:
    """Save settings using the existing PascalCase config format."""

    path.write_text(
        f"TargetDirectory: '{settings.target_directory}'\n"
        f"GrowthThresholdMB: {settings.growth_threshold_mb}\n"
        f"HistoryDays: {settings.history_days}\n"
        f"DatabasePath: '{settings.database_path}'\n",
        encoding="utf-8",
    )


def settings_to_legacy_dict(settings: AppSettings) -> dict[str, Any]:
    """Return the old dictionary shape used by the original GUI module."""

    return {
        "TargetDirectory": str(settings.target_directory),
        "GrowthThresholdMB": settings.growth_threshold_mb,
        "HistoryDays": settings.history_days,
        "DatabasePath": str(settings.database_path),
    }
