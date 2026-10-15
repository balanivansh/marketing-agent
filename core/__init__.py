"""Core module for Marketing OS."""

from core.config import settings, get_brand_dir, get_brand_config_path, get_brand_db_path, load_brand_config
from core.db import clear_research_items, get_db_connection, get_db_session, get_existing_tables, init_db
from core.logger import logfire, logger
from core.router import call_llm, LLMError
from core.schemas import (
    BrandConfig,
    Draft,
    DraftDiff,
    LLMEngine,
    LLMResponse,
    LLMTaskType,
    ResearchItem,
    StyleObservation,
)

__all__ = [
    "settings",
    "get_brand_dir",
    "get_brand_config_path",
    "get_brand_db_path",
    "load_brand_config",
    "init_db",
    "get_db_connection",
    "get_db_session",
    "get_existing_tables",
    "logfire",
    "logger",
    "call_llm",
    "LLMError",
    "BrandConfig",
    "Draft",
    "DraftDiff",
    "LLMEngine",
    "LLMResponse",
    "LLMTaskType",
    "ResearchItem",
    "StyleObservation",
]
