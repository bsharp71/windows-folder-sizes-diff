from pathlib import Path

import pytest

from windows_folder_sizes_diff.config import AppSettings, load_settings, save_settings


def test_defaults_load_when_config_missing(tmp_path: Path) -> None:
    settings = load_settings(tmp_path / "missing.yaml")

    assert settings.target_directory == Path("C:/")
    assert settings.growth_threshold_mb == 100
    assert settings.history_days == 1


def test_valid_settings_load_correctly(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "TargetDirectory: 'C:\\Windows\\Temp'\n"
        "GrowthThresholdMB: 250\n"
        "HistoryDays: 7\n",
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.target_directory == Path("C:\\Windows\\Temp")
    assert settings.growth_threshold_mb == 250
    assert settings.history_days == 7


def test_invalid_threshold_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "TargetDirectory: 'C:\\Temp'\nGrowthThresholdMB: -1\nHistoryDays: 1\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="GrowthThresholdMB"):
        load_settings(config_path)


def test_invalid_history_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "TargetDirectory: 'C:\\Temp'\nGrowthThresholdMB: 1\nHistoryDays: 0\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="HistoryDays"):
        load_settings(config_path)


def test_settings_save_and_reload(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    original = AppSettings(
        target_directory=Path("C:\\Temp"),
        growth_threshold_mb=42,
        history_days=3,
    )

    save_settings(original, config_path)
    loaded = load_settings(config_path)

    assert loaded == original


def test_paths_containing_spaces_are_preserved(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    path_with_spaces = Path("C:\\Users\\Example User\\Temp Files")

    save_settings(
        AppSettings(
            target_directory=path_with_spaces,
            growth_threshold_mb=1,
            history_days=1,
        ),
        config_path,
    )

    assert load_settings(config_path).target_directory == path_with_spaces
