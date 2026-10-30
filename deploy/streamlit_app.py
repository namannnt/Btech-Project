"""Streamlit Community Cloud entry point (no separate backend required)."""

import os
from pathlib import Path
import runpy
import sys

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# Root-level Streamlit secrets become environment variables before backend imports.
try:
    for key, value in st.secrets.items():
        if isinstance(value, (str, int, float, bool)):
            os.environ[key.upper()] = str(value)
except FileNotFoundError:
    pass

os.environ["NL2SQL_EMBEDDED_API"] = "1"
os.environ.setdefault("DEBUG", "false")
# Cloud uses the existing full-schema fallback to avoid loading a local embedding
# model into limited Community Cloud memory. Local installations retain RAG.
os.environ.setdefault("ENABLE_SCHEMA_RAG", "false")

from backend.core.config import settings
from sqlalchemy.engine import make_url
from scripts.create_sample_db import create_db

url = make_url(settings.database_url)
if url.drivername == "sqlite" and url.database and Path(url.database).name == "sample.db":
    create_db(url.database, overwrite=False, remove_alternate=False)

runpy.run_path(str(ROOT / "frontend" / "app.py"), run_name="__main__")
