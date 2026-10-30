import os
from dataclasses import dataclass, field
from pathlib import Path


# Load only the two supported settings from the ignored project-root .env.
# Existing process environment values take precedence; never print the values.
def load_local_env():
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key in {"OPENAI_API_KEY", "OPENAI_MODEL"}:
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            # Model always follows the project .env so local restarts pick up changes
            # even when a parent shell still has a stale OPENAI_MODEL value.
            if key == "OPENAI_MODEL":
                os.environ[key] = value
            else:
                os.environ.setdefault(key, value)


load_local_env()


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.getenv("DATA_DIR", "data")).resolve()
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024
    max_files: int = 10
    max_attempts: int = 3
    lease_seconds: int = 120
    retry_base_seconds: int = 5
    poll_seconds: float = 1.0
    cors_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""), repr=False)
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-5-nano"))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "documents.sqlite3"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"
