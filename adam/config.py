"""Configuration settings for ADAM."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Database configuration
def get_database_url() -> str:
    return os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'adam.db'}")

DATABASE_URL = get_database_url()

# Storage configuration
def get_storage_dir() -> Path:
    return Path(os.getenv("STORAGE_DIR", str(BASE_DIR / ".adam_storage")))

STORAGE_DIR = get_storage_dir()

# Collector / Ingestion
COLLECTOR_VERSION = "0.1.0"
DEFAULT_USER_AGENT = (
    "ADAM-Uttarakhand-Public-Records-Collector/0.1.0 "
    "(+https://uk.gov.in; departmental-authorised-crawler)"
)

# Cryptographic signing secret for inventory manifests
SIGNING_SECRET = os.getenv("SIGNING_SECRET", "adam-uk-gov-default-auth-secret-key-2026")

# Maximum permitted file size for ingestion (e.g., 200MB)
MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024

# Default request timeout in seconds
REQUEST_TIMEOUT_SECONDS = 30.0
