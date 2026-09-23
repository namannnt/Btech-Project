"""
Schema Service

Encapsulates ChromaDB embedding and retrieval logic for the Schema Retrieval Agent.
Handles:
- Embedding model initialization
- ChromaDB collection management
- Indexing table schemas as documents
- Semantic retrieval of relevant tables for a given query
"""

from typing import Any, Dict, List, Optional
from backend.core.config import settings


class SchemaService:
    """
    Service for ChromaDB-backed schema embedding, indexing, and retrieval.
    """

    def __init__(self) -> None:
        self._client = None
        self._collection = None
        self._embeddings = None
        self._cached_schema: Optional[Dict[str, Any]] = None
        self._initialized = False

    def initialize(self) -> bool:
        """
        Lazily initialize embeddings and ChromaDB client.

        Returns:
            True if initialization succeeded.
        """
        if self._initialized:
            return True

        try:
            from langchain_community.embeddings import HuggingFaceEmbeddings
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            self._embeddings = HuggingFaceEmbeddings(
                model_name=settings.embedding_model,
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )

            chroma_settings = ChromaSettings(
                persist_directory=settings.chroma_persist_dir,
                anonymized_telemetry=False,
            )
            self._client = chromadb.Client(chroma_settings)
            self._collection = self._client.get_or_create_collection(
                name="database_schemas",
                metadata={"hnsw:space": "cosine"},
            )
            self._initialized = True
            return True

        except Exception as e:
            print(f"[SchemaService] Initialization failed: {e}")
            return False

    def index_schema(self, schema: Dict[str, Any]) -> int:
        """
        Index table schemas into ChromaDB.

        Args:
            schema: Output of DatabaseService.introspect()

        Returns:
            Number of tables indexed.
        """
        if not self.initialize() or not self._collection:
            return 0

        self._cached_schema = schema
        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []
        ids: List[str] = []

        for table_name, table_info in schema.get("tables", {}).items():
            col_desc = ", ".join(
                f"{c['name']} ({c['type']})" for c in table_info.get("columns", [])
            )
            doc = f"Table: {table_name}. Columns: {col_desc}."

            # Add FK context
            table_fks = [
                fk
                for fk in schema.get("foreign_keys", [])
                if fk["table"] == table_name or fk["referenced_table"] == table_name
            ]
            if table_fks:
                fk_desc = "; ".join(
                    f"{fk['table']}.{fk['column']} -> {fk['referenced_table']}.{fk['referenced_column']}"
                    for fk in table_fks
                )
                doc += f" Relationships: {fk_desc}."

            documents.append(doc)
            metadatas.append({
                "table_name": table_name,
                "column_count": table_info.get("column_count", 0),
                "source": "database_schema",
            })
            ids.append(f"table_{table_name}")

        if documents:
            self._collection.add(documents=documents, metadatas=metadatas, ids=ids)

        return len(documents)

    def retrieve(
        self,
        query: str,
        intent: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """
        Retrieve the most semantically relevant tables for a query.

        Args:
            query: Natural language question
            intent: Parsed intent from Agent 1 (used to enhance query)
            top_k: Maximum number of relevant tables to return

        Returns:
            {"relevant_tables", "table_schemas", "foreign_keys", "relevance_scores"}
        """
        if not self.initialize() or not self._collection:
            return {
                "relevant_tables": [],
                "table_schemas": {},
                "foreign_keys": [],
                "relevance_scores": {},
            }

        # Enhance query with intent entities
        enhanced_query = query
        if intent:
            entities = intent.get("entities", [])
            if entities:
                enhanced_query = f"{query}. Mentions: {', '.join(entities)}"

        results = self._collection.query(
            query_texts=[enhanced_query],
            n_results=min(top_k * 2, max(1, self._collection.count())),
            include=["documents", "metadatas", "distances"],
        )

        relevant_tables: List[str] = []
        relevance_scores: Dict[str, float] = {}

        if results and results.get("metadatas"):
            for i, metadata in enumerate(results["metadatas"][0]):
                table_name = metadata["table_name"]
                distance = results["distances"][0][i] if results.get("distances") else 1.0
                similarity = max(0.0, 1.0 - float(distance))
                relevant_tables.append(table_name)
                relevance_scores[table_name] = similarity

        # Get schema details from cache
        table_schemas: Dict[str, Any] = {}
        relevant_fks: List[Dict[str, str]] = []

        if self._cached_schema:
            for table_name in relevant_tables[:top_k]:
                if table_name in self._cached_schema.get("tables", {}):
                    table_schemas[table_name] = self._cached_schema["tables"][table_name]

            relevant_fks = [
                fk
                for fk in self._cached_schema.get("foreign_keys", [])
                if fk["table"] in relevant_tables[:top_k]
                or fk["referenced_table"] in relevant_tables[:top_k]
            ]

        return {
            "relevant_tables": relevant_tables[:top_k],
            "table_schemas": table_schemas,
            "foreign_keys": relevant_fks,
            "relevance_scores": relevance_scores,
        }


# Singleton
_schema_service: Optional[SchemaService] = None


def get_schema_service() -> SchemaService:
    """Return the global SchemaService instance."""
    global _schema_service
    if _schema_service is None:
        _schema_service = SchemaService()
    return _schema_service
