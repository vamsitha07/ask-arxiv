"""Runtime configuration. Everything overridable by environment variable."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# arXiv asks that harvesters identify themselves and back off when told to.
# https://info.arxiv.org/help/oa/index.html
OAI_ENDPOINT = os.getenv("ARXIV_OAI_ENDPOINT", "http://export.arxiv.org/oai2")
USER_AGENT = os.getenv(
    "ARXIV_USER_AGENT",
    "askarxiv/0.1 (+https://github.com/vamsitha07/ask-arxiv; mailto:vamsitha7@gmail.com)",
)

# arXiv returns 503 with Retry-After when it wants you to slow down. Honour it.
DEFAULT_RETRY_AFTER = int(os.getenv("ARXIV_DEFAULT_RETRY_AFTER", "20"))
MAX_RETRIES = int(os.getenv("ARXIV_MAX_RETRIES", "8"))
REQUEST_TIMEOUT = int(os.getenv("ARXIV_REQUEST_TIMEOUT", "60"))

# One request per second is sustainable and keeps us out of the 429 zone.
MIN_REQUEST_INTERVAL = float(os.getenv("ARXIV_MIN_REQUEST_INTERVAL", "1.0"))

STATE_DIR = Path(os.getenv("ASKARXIV_STATE_DIR", REPO_ROOT / ".state"))
DATA_DIR = Path(os.getenv("ASKARXIV_DATA_DIR", REPO_ROOT / "data"))


@dataclass(frozen=True)
class DbConfig:
    host: str = os.getenv("PGHOST", "localhost")
    port: int = int(os.getenv("PGPORT", "5433"))
    user: str = os.getenv("PGUSER", "askarxiv")
    password: str = os.getenv("PGPASSWORD", "askarxiv")
    database: str = os.getenv("PGDATABASE", "askarxiv")

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
