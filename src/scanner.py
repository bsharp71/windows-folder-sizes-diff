import os
import threading
from datetime import datetime, timedelta
from pathlib import Path


SIDECAR_PATH = Path(__file__).parent.parent / "CheckFolderGrowth.yaml"
LOGS_DIR = Path(__file__).parent.parent / "logs"
DEFAULTS = {"TargetDirectory": "C:\\", "GrowthThresholdMB": 100, "HistoryDays": 1}


def load_settings() -> dict:
    settings = dict(DEFAULTS)
    if SIDECAR_PATH.exists():
        for line in SIDECAR_PATH.read_text().splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                settings[key.strip()] = val.strip().strip("'")
    settings["GrowthThresholdMB"] = int(settings["GrowthThresholdMB"])
    settings["HistoryDays"] = int(settings["HistoryDays"])
    return settings


def save_settings(target_dir: str, threshold_mb: int, history_days: int):
    SIDECAR_PATH.write_text(
        f"TargetDirectory: '{target_dir}'\n"
        f"GrowthThresholdMB: {threshold_mb}\n"
        f"HistoryDays: {history_days}\n"
    )


class FolderScanner:
    def __init__(self, target_dir: str, threshold_mb: int, history_days: int,
                 on_status, on_result, on_complete):
        self._target_dir = target_dir
        self._threshold_bytes = threshold_mb * 1024 * 1024
        self._since = datetime.now() - timedelta(days=history_days)
        self._history_days = history_days
        self._on_status = on_status
        self._on_result = on_result
        self._on_complete = on_complete
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def _run(self):
        start = datetime.now()
        log_lines = []

        def elapsed():
            return int((datetime.now() - start).total_seconds())

        # Phase 1: build folder list via BFS
        folders = []
        queue = [self._target_dir]
        while queue and not self._stop_event.is_set():
            current = queue.pop(0)
            try:
                children = list(os.scandir(current))
            except PermissionError:
                continue
            for entry in children:
                if entry.is_dir(follow_symlinks=False):
                    queue.append(entry.path)
                    folders.append(entry.path)
            self._on_status(f"Building folder list... ({len(folders)} found)  {elapsed()}s")

        if self._stop_event.is_set():
            self._on_complete(log_lines, cancelled=True)
            return

        # Phase 2: analyze each folder
        total = len(folders)
        flagged = 0
        for i, folder in enumerate(folders, 1):
            if self._stop_event.is_set():
                break
            self._on_status(f"Analyzing {i} of {total}  {elapsed()}s")
            try:
                new_bytes = sum(
                    e.stat().st_size
                    for e in os.scandir(folder)
                    if e.is_file(follow_symlinks=False)
                    and max(e.stat().st_mtime, e.stat().st_ctime) > self._since.timestamp()
                )
            except PermissionError:
                continue

            if new_bytes >= self._threshold_bytes:
                mb = round(new_bytes / 1024 / 1024, 2)
                msg = f"{folder}  →  {mb} MB in last {self._history_days} day(s)"
                self._on_result(folder, mb)
                log_lines.append(msg)
                flagged += 1

        self._on_complete(log_lines, cancelled=self._stop_event.is_set(), flagged=flagged, total=total)

    @staticmethod
    def write_log(log_lines: list[str], target_dir: str, threshold_mb: int, history_days: int):
        LOGS_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_path = LOGS_DIR / f"scan_{timestamp}.log"
        header = (
            f"Scan run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Target: {target_dir}\n"
            f"Threshold: {threshold_mb} MB\n"
            f"History: {history_days} day(s)\n"
            f"{'─' * 60}\n"
        )
        log_path.write_text(header + "\n".join(log_lines) + "\n", encoding="utf-8")
        return log_path
