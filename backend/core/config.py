"""
Configuration management for the NL2SQL 8-Agent System.

Loads environment variables and provides type-safe configuration.
All variables defined here have matching entries in .env.example.
"""

from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Priority order (highest to lowest):
    1. Actual environment variables (e.g. set in shell)
    2. .env file values
    3. Defaults defined here
    """

    # -------------------------------------------------------------------------
    # LLM API Keys (never committed — loaded from .env)
    # -------------------------------------------------------------------------
    openai_api_key: str = ""
    groq_api_key: str = ""

    # -------------------------------------------------------------------------
    # Database Connection Strings
    # -------------------------------------------------------------------------
    # SQLite is the default local database; Postgres/MySQL override it when set
    sqlite_url: str = "sqlite:///./data/sample.db"
    postgres_url: str = ""
    mysql_url: str = ""

    # -------------------------------------------------------------------------
    # Vector Store (ChromaDB) Configuration
    # -------------------------------------------------------------------------
    chroma_persist_dir: str = "./data/chroma_db"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # -------------------------------------------------------------------------
    # LLM Model Configuration
    # -------------------------------------------------------------------------
    primary_llm_model: str = "gpt-4o-mini"                         # OpenAI
    fallback_llm_model: str = "llama-3.1-70b-versatile"            # Groq
    explanation_llm_model: str = "llama-3.1-8b-instant"            # Groq (light)

    # -------------------------------------------------------------------------
    # Query Execution Limits
    # -------------------------------------------------------------------------
    max_query_timeout: int = 30        # Seconds before query is killed
    max_rows_returned: int = 1000      # Hard cap on result rows

    # -------------------------------------------------------------------------
    # Security & Permissions
    # -------------------------------------------------------------------------
    default_role: str = "user"
    secret_key: str = "change-me-in-production"

    # -------------------------------------------------------------------------
    # Application Metadata
    # -------------------------------------------------------------------------
    app_name: str = "NL2SQL Multi-Agent System"
    app_version: str = "1.0.0"
    api_v1_prefix: str = "/api/v1"
    debug: bool = True
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False
        # Allow extra fields so unknown env vars don't cause validation errors
        extra = "ignore"

    # -------------------------------------------------------------------------
    # Computed properties
    # -------------------------------------------------------------------------

    @property
    def database_url(self) -> str:
        """
        Returns the primary database URL based on which env vars are set.

        Priority: DATABASE_URL (legacy) > POSTGRES_URL > MYSQL_URL > SQLITE_URL
        """
        # Legacy single-variable override
        legacy = os.getenv("DATABASE_URL", "")
        if legacy:
            return legacy

        if self.postgres_url:
            return self.postgres_url
        if self.mysql_url:
            return self.mysql_url
        return self.sqlite_url

    @property
    def use_openai(self) -> bool:
        """True if a valid OpenAI API key is configured."""
        return bool(
            self.openai_api_key
            and self.openai_api_key not in ("", "your_openai_api_key_here")
        )

    @property
    def use_groq(self) -> bool:
        """True if a valid Groq API key is configured."""
        return bool(
            self.groq_api_key
            and self.groq_api_key not in ("", "your_groq_api_key_here")
        )


# Global singleton
settings = Settings()


def get_settings() -> Settings:
    """Return the global Settings instance."""
    return settings


def get_dynamic_db_url(database_id: Optional[str] = None) -> str:
    """Resolve database_id to a safe SQLite connection URL."""
    if not database_id or database_id == "sample":
        return settings.database_url
    
    import re
    import os
    clean_id = re.sub(r'[^a-zA-Z0-9_-]', '', database_id)
    db_path = os.path.abspath(f"backend/data/{clean_id}.db")
    # Replace backslashes for Windows path in SQLAlchemy URL
    db_path = db_path.replace('\\', '/')
    return f"sqlite:///{db_path}"
