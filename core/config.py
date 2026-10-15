"""Configuration and path resolution for Marketing OS."""

from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.schemas import BrandConfig

# Project root directory (the parent of core/)
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file if it exists
load_dotenv(dotenv_path=BASE_DIR / ".env")


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    LOGFIRE_TOKEN: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"
    OLLAMA_KEEP_ALIVE: str = "1m"
    GEMINI_MODEL: str = "gemini-2.5-flash"
    LLM_TIMEOUT_SECONDS: float = 60.0

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


def get_brand_dir(tenant_id: str) -> Path:
    """Resolve the directory for a tenant brand: brands/{tenant_id}/."""
    return BASE_DIR / "brands" / tenant_id


def get_brand_config_path(tenant_id: str) -> Path:
    """Resolve the configuration path: brands/{tenant_id}/brand.json."""
    return get_brand_dir(tenant_id) / "brand.json"


def get_brand_db_path(tenant_id: str) -> Path:
    """Resolve the SQLite database path: brands/{tenant_id}/brand.db."""
    return get_brand_dir(tenant_id) / "brand.db"


def get_brand_templates_dir(tenant_id: str) -> Path:
    """Resolve the templates directory: brands/{tenant_id}/templates/."""
    return get_brand_dir(tenant_id) / "templates"


def load_brand_config(tenant_id: str) -> BrandConfig:
    """Load and validate brand.json for a given tenant_id against BrandConfig."""
    config_path = get_brand_config_path(tenant_id)
    if not config_path.exists():
        raise FileNotFoundError(f"Brand configuration file not found at: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        return BrandConfig.model_validate_json(f.read())
