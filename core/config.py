from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field
from platformdirs import user_data_dir


def _default_data_dir() -> Path:
    return Path(user_data_dir("caibinet", "caibinet"))


class Settings(BaseSettings):
    # Server
    port: int = Field(default=8765, alias="CAIBINET_PORT")

    # Data storage
    data_dir: Path = Field(default_factory=_default_data_dir)

    # Ollama
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"
    ollama_timeout: int = 120

    # Scan
    ignore_patterns: List[str] = ["*.tmp", "*.log", ".DS_Store", "node_modules/**"]
    max_files: int = 1  # 0 = no limit
    context_aware: bool = False  # Pass full file list to LLM for more conservative decisions
    summary_cache_ttl_minutes: int = 1440  # 0 = cache disabled (1440 = 1 day)
    ocr_enabled: bool = False  # Run Tesseract OCR on image files (requires tesseract-ocr system package)

    class Config:
        env_prefix = "CAIBINET_"
        env_file = ".env"
        populate_by_name = True

    @property
    def db_path(self) -> Path:
        return self.data_dir / "caibinet.db"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    def ensure_data_dir(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


# Global settings instance – overridden in tests via dependency injection
settings = Settings()
