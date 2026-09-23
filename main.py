#!/usr/bin/env python3
"""
NL2SQL Multi-Agent System — Root Entry Point

Usage:
    python main.py              # Start the API server
    python main.py --frontend   # Start the Streamlit frontend
"""

import sys


def start_api():
    """Start the FastAPI backend server."""
    import uvicorn
    from backend.core.config import settings
    print(f"Starting {settings.app_name} v{settings.app_version}")
    print("=" * 60)
    print("API Docs:     http://localhost:8000/docs")
    print("Health check: http://localhost:8000/api/v1/health")
    print("Main endpoint: POST http://localhost:8000/api/v1/query")
    print("=" * 60)
    uvicorn.run(
        "backend.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )


def start_frontend():
    """Launch the Streamlit frontend."""
    import subprocess
    subprocess.run(["streamlit", "run", "frontend/app.py"], check=True)


if __name__ == "__main__":
    if "--frontend" in sys.argv:
        start_frontend()
    else:
        start_api()
