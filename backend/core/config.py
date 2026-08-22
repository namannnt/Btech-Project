"""
Configuration management for the NL2SQL Multi-Agent System.
Loads environment variables and provides type-safe configuration access.
"""

from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # LLM API Keys
    openai_api_key: str = ""
    groq_api_key: str = ""
    
    # Database Connection Strings
    postgres_url: str = "sqlite:///./data/sample.db"
    mysql_url: str = ""
    sqlite_url: str = "sqlite:///./data/sample.db"
    
    # Vector Store Configuration
    chroma_persist_dir: str = "./data/chroma_db"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    
    # LLM Model Configuration
    primary_llm_model: str = "gpt-4o-mini"
    fallback_llm_model: str = "llama-3.1-70b-versatile"
    
    # Query Execution Limits
    max_query_timeout: int = 30
    max_rows_returned: int = 1000
    
    # Security & Permissions
    default_role: str = "user"
    secret_key: str = "your-secret-key-change-in-production"
    
    # Application Settings
    debug: bool = True
    log_level: str = "INFO"
    
    # Application metadata
    app_name: str = "NL2SQL Multi-Agent System"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    @property
    def database_url(self) -> str:
        """Returns the primary database URL based on availability."""
        if os.getenv("POSTGRES_URL"):
            return self.postgres_url
        elif os.getenv("MYSQL_URL"):
            return self.mysql_url
        else:
            return self.sqlite_url
    
    @property
    def use_openai(self) -> bool:
        """Check if OpenAI API key is configured."""
        return bool(self.openai_api_key and self.openai_api_key != "your_openai_api_key_here")
    
    @property
    def use_groq(self) -> bool:
        """Check if Groq API key is configured."""
        return bool(self.groq_api_key and self.groq_api_key != "your_groq_api_key_here")


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings
