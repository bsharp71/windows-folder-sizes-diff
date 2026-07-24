"""Central application paths and constants."""

from pathlib import Path

APP_VERSION = "0.3.3"
PACKAGE_DIR = Path(__file__).resolve().parent
SRC_DIR = PACKAGE_DIR.parent
PROJECT_ROOT = SRC_DIR.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
LOGS_DIR = PROJECT_ROOT / "logs"
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DATABASE_PATH = Path("data/folder_sizes.db")
APPLICATION_LOG_PATH = LOGS_DIR / "application.log"
