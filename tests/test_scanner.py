import os
import stat
import time
from types import SimpleNamespace
from pathlib import Path

from windows_folder_sizes_diff.scanner.events import (
    FolderMatched,
    FolderObserved,
    ScanCompleted,
    ScanWarning,
)
from windows_folder_sizes_diff.scanner.folder_scanner import FolderScanner
from windows_folder_sizes_diff.scanner.models import ScanRequest


def run_scan(request: ScanRequest) -> list[object]:
    events: list[object] = []
    scanner = FolderScanner(request=request, event_sink=events.append)
    scanner.start()
    scanner.wait(5)
    assert not scanner.is_running
    return events


def completion(events: list[object]) -> ScanCompleted:
    completions = [event for event in events if isinstance(event, ScanCompleted)]
    assert len(completions) == 1
    return completions[0]


def write_file(path: Path, size: int) -> None:
    path.write_bytes(b"x" * size)


def test_recent_file_above_threshold_emits_match(tmp_path: Path) -> None:
    write_file(tmp_path / "recent.bin", 2 * 1024 * 1024)

    events = run_scan(
        ScanRequest(target_directory=tmp_path, growth_threshold_mb=1, history_days=1)
    )

    matches = [event for event in events if isinstance(event, FolderMatched)]
    assert [match.folder for match in matches] == [tmp_path]
    assert matches[0].matching_bytes == 2 * 1024 * 1024


def test_old_file_is_excluded(tmp_path: Path, monkeypatch) -> None:
    old_timestamp = time.time() - (3 * 24 * 60 * 60)

    class FakeEntry:
        path = str(tmp_path / "old.bin")

        def is_dir(self, follow_symlinks=False):
            return False

        def stat(self, follow_symlinks=False):
            return SimpleNamespace(
                st_mode=stat.S_IFREG,
                st_size=2 * 1024 * 1024,
                st_mtime=old_timestamp,
                st_ctime=old_timestamp,
            )

    monkeypatch.setattr(
        "windows_folder_sizes_diff.scanner.folder_scanner.os.scandir",
        lambda path: [FakeEntry()],
    )

    events = run_scan(
        ScanRequest(target_directory=tmp_path, growth_threshold_mb=1, history_days=1)
    )

    assert not [event for event in events if isinstance(event, FolderMatched)]


def test_modified_same_size_file_is_included_by_phase_0_semantics(tmp_path: Path) -> None:
    file_path = tmp_path / "same-size.bin"
    write_file(file_path, 2 * 1024 * 1024)
    old_timestamp = time.time() - (3 * 24 * 60 * 60)
    os.utime(file_path, (old_timestamp, old_timestamp))
    current_timestamp = time.time()
    os.utime(file_path, (current_timestamp, current_timestamp))

    events = run_scan(
        ScanRequest(target_directory=tmp_path, growth_threshold_mb=1, history_days=1)
    )

    matches = [event for event in events if isinstance(event, FolderMatched)]
    assert len(matches) == 1
    assert matches[0].matching_bytes == 2 * 1024 * 1024


def test_nested_folders_and_target_root_are_observed(tmp_path: Path) -> None:
    nested = tmp_path / "child" / "grandchild"
    nested.mkdir(parents=True)

    events = run_scan(
        ScanRequest(target_directory=tmp_path, growth_threshold_mb=100, history_days=1)
    )

    observed = {
        event.observation.path for event in events if isinstance(event, FolderObserved)
    }
    assert tmp_path in observed
    assert tmp_path / "child" in observed
    assert nested in observed


def test_permission_or_enumeration_failure_emits_warning_and_continues(
    tmp_path: Path, monkeypatch
) -> None:
    bad = tmp_path / "bad"
    good = tmp_path / "good"
    bad.mkdir()
    good.mkdir()
    original_scandir = os.scandir

    def fake_scandir(path):
        if Path(path) == bad:
            raise PermissionError("denied")
        return original_scandir(path)

    monkeypatch.setattr(
        "windows_folder_sizes_diff.scanner.folder_scanner.os.scandir",
        fake_scandir,
    )

    events = run_scan(
        ScanRequest(target_directory=tmp_path, growth_threshold_mb=100, history_days=1)
    )

    warnings = [event for event in events if isinstance(event, ScanWarning)]
    observed = {
        event.observation.path for event in events if isinstance(event, FolderObserved)
    }
    assert any(warning.path == bad for warning in warnings)
    assert good in observed
    assert completion(events).warning_count == len(warnings)


def test_file_disappears_during_scan_emits_warning(tmp_path: Path, monkeypatch) -> None:
    class FakeEntry:
        path = str(tmp_path / "missing.bin")

        def is_dir(self, follow_symlinks=False):
            return False

        def stat(self, follow_symlinks=False):
            raise FileNotFoundError("gone")

    monkeypatch.setattr(
        "windows_folder_sizes_diff.scanner.folder_scanner.os.scandir",
        lambda path: [FakeEntry()],
    )

    events = run_scan(
        ScanRequest(target_directory=tmp_path, growth_threshold_mb=100, history_days=1)
    )

    warnings = [event for event in events if isinstance(event, ScanWarning)]
    assert any(warning.operation == "stat_file" for warning in warnings)
    assert completion(events).warning_count == 1


def test_cancellation_produces_one_cancelled_completion(tmp_path: Path, monkeypatch) -> None:
    for index in range(200):
        folder = tmp_path / f"folder-{index}"
        folder.mkdir()
        write_file(folder / "file.bin", 1)

    original_analyze_folder = FolderScanner._analyze_folder

    def slow_analyze_folder(self, folder, cutoff_timestamp):
        time.sleep(0.005)
        return original_analyze_folder(self, folder, cutoff_timestamp)

    monkeypatch.setattr(FolderScanner, "_analyze_folder", slow_analyze_folder)
    events: list[object] = []
    scanner = FolderScanner(
        request=ScanRequest(target_directory=tmp_path, growth_threshold_mb=100, history_days=1),
        event_sink=events.append,
    )

    scanner.start()
    time.sleep(0.02)
    scanner.stop()
    scanner.wait(5)

    completions = [event for event in events if isinstance(event, ScanCompleted)]
    assert len(completions) == 1
    assert completions[0].cancelled is True


def test_no_duplicate_completion(tmp_path: Path) -> None:
    events = run_scan(
        ScanRequest(target_directory=tmp_path, growth_threshold_mb=100, history_days=1)
    )

    assert len([event for event in events if isinstance(event, ScanCompleted)]) == 1
