# Streamlit Community Cloud

Deploy `namannnt/Btech-Project`, branch `codex/streamlit-cloud`, entry point
`deploy/streamlit_app.py`. Select Python 3.12 in Advanced settings.

The entry point hosts the existing FastAPI API in process, preserving the upload
and query endpoints without an external server. It creates the sample SQLite
database only if missing, and never overwrites an existing database.

Add root-level secrets in Streamlit Advanced settings (never in Git):

```toml
OPENAI_API_KEY = "your-key"
# Optional fallback provider:
GROQ_API_KEY = "your-key"
```

Deployment works without keys: the interface and database uploads remain
available, and AI chat is disabled until a provider key is added.
At least one working provider key is required for SQL generation. Existing
environment/model configuration keys are supported. Secrets must be configured
before starting the app; reboot the app after changing them.

Cloud dependencies are in `deploy/requirements.txt`. The cloud configuration
uses the existing direct schema introspection fallback instead of downloading
ChromaDB/embedding models, reducing memory use. The eight agent stages remain
active. Local `frontend/app.py` behavior and default semantic RAG are preserved.

SQLite files and uploads are ephemeral on Community Cloud and may disappear on
reboot/redeploy. Use sample data or re-upload a database after restart.

Local preview: `streamlit run deploy/streamlit_app.py`.
