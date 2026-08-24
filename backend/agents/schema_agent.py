"""
Agent 2: Schema Retrieval (RAG-based)

This agent retrieves relevant database schema information using RAG (Retrieval-Augmented Generation):
1. Embeds the user question + parsed intent
2. Searches ChromaDB for relevant table schemas
3. Returns filtered schema with only relevant tables/columns
4. Includes foreign key relationships for JOIN detection

This implements "schema pruning" from AST-Ranking paper + Selector agent from MAC-SQL.
Reduces context sent to SQL generation LLM, improving accuracy and reducing costs.
"""

import json
from typing import Dict, Any, List, Optional
from langchain_core.prompts import ChatPromptTemplate
from backend.core.config import settings
from backend.agents.state import AgentState, add_to_processing_log


class SchemaRetrievalAgent:
    """
    Agent 2: Schema Retrieval
    
    Uses RAG with ChromaDB to retrieve only relevant schema information.
    This is critical for large databases where sending full schema to LLM is:
    - Expensive (token costs)
    - Confusing (too much context reduces accuracy)
    - Slow (larger prompts = slower generation)
    """
    
    def __init__(self):
        """Initialize the Schema Retrieval Agent."""
        self.chroma_client = None
        self.collection = None
        self.embeddings = None
        self.db_engine = None
        self._initialized = False
    
    def _initialize(self):
        """Lazy initialization of ChromaDB and embeddings."""
        if self._initialized:
            return
        
        try:
            # Initialize embeddings
            from langchain_community.embeddings import HuggingFaceEmbeddings
            self.embeddings = HuggingFaceEmbeddings(
                model_name=settings.embedding_model,
                model_kwargs={'device': 'cpu'},
                encode_kwargs={'normalize_embeddings': True}
            )
            
            # Initialize ChromaDB
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            
            chroma_settings = ChromaSettings(
                persist_directory=settings.chroma_persist_dir,
                anonymized_telemetry=False
            )
            
            self.chroma_client = chromadb.Client(chroma_settings)
            self.collection = self.chroma_client.get_or_create_collection(
                name="database_schemas",
                metadata={"hnsw:space": "cosine"}
            )
            
            self._initialized = True
            
        except Exception as e:
            print(f"Warning: Schema retrieval initialization failed: {e}")
            self._initialized = False
    
    def connect_to_database(self, db_url: Optional[str] = None):
        """
        Connect to the target database for schema introspection.
        
        Args:
            db_url: Database connection URL (uses default from config if not provided)
        """
        from sqlalchemy import create_engine, inspect
        
        if not db_url:
            db_url = settings.database_url
        
        try:
            self.db_engine = create_engine(db_url)
            self.inspector = inspect(self.db_engine)
            return True
        except Exception as e:
            print(f"Database connection failed: {e}")
            return False
    
    def introspect_schema(self) -> Dict[str, Any]:
        """
        Introspect the connected database to extract schema information.
        
        Returns:
            Dictionary containing tables, columns, types, and foreign keys
        """
        if not self.db_engine:
            return {}
        
        schema_info = {
            "tables": {},
            "foreign_keys": []
        }
        
        try:
            # Get all table names
            table_names = self.inspector.get_table_names()
            
            for table_name in table_names:
                # Get columns
                columns = self.inspector.get_columns(table_name)
                column_info = [
                    {
                        "name": col["name"],
                        "type": str(col["type"]),
                        "nullable": col.get("nullable", True),
                        "primary_key": col.get("primary_key", False)
                    }
                    for col in columns
                ]
                
                # Get foreign keys
                fkeys = self.inspector.get_foreign_keys(table_name)
                for fk in fkeys:
                    schema_info["foreign_keys"].append({
                        "table": table_name,
                        "column": fk["constrained_columns"][0],
                        "referenced_table": fk["referred_table"],
                        "referenced_column": fk["referred_columns"][0]
                    })
                
                schema_info["tables"][table_name] = {
                    "columns": column_info,
                    "column_count": len(column_info)
                }
            
            return schema_info
            
        except Exception as e:
            print(f"Schema introspection failed: {e}")
            return {}
    
    def index_schema(self, schema_info: Dict[str, Any]):
        """
        Index the database schema into ChromaDB for retrieval.
        
        Args:
            schema_info: Schema information from introspect_schema()
        """
        if not self._initialized:
            self._initialize()
        
        if not self.collection:
            print("ChromaDB collection not available")
            return
        
        # Cache the schema for later retrieval (avoids re-introspection)
        self._cached_schema = schema_info
        
        documents = []
        metadatas = []
        ids = []
        
        # Create a document for each table
        for table_name, table_info in schema_info["tables"].items():
            # Create a text representation of the table schema
            column_descriptions = ", ".join(
                f"{col['name']} ({col['type']})" 
                for col in table_info["columns"]
            )
            
            doc_text = f"Table: {table_name}. Columns: {column_descriptions}."
            
            # Add foreign key relationships
            table_fks = [
                fk for fk in schema_info["foreign_keys"] 
                if fk["table"] == table_name or fk["referenced_table"] == table_name
            ]
            
            if table_fks:
                fk_descriptions = []
                for fk in table_fks:
                    if fk["table"] == table_name:
                        fk_descriptions.append(
                            f"References {fk['referenced_table']}({fk['referenced_column']})"
                        )
                    else:
                        fk_descriptions.append(
                            f"Referenced by {fk['table']}({fk['column']})"
                        )
                doc_text += " Relationships: " + "; ".join(fk_descriptions) + "."
            
            documents.append(doc_text)
            metadatas.append({
                "table_name": table_name,
                "column_count": table_info["column_count"],
                "source": "database_schema"
            })
            ids.append(f"table_{table_name}")
        
        # Add to ChromaDB
        if documents:
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            print(f"Indexed {len(documents)} tables into ChromaDB")
    
    def retrieve_relevant_schema(
        self, 
        query: str, 
        intent: Optional[Dict[str, Any]] = None,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        Retrieve the most relevant table schemas for the given query.
        
        Args:
            query: User's natural language question
            intent: Parsed intent from Agent 1
            top_k: Number of top relevant tables to retrieve
            
        Returns:
            Relevant schema information
        """
        if not self._initialized:
            self._initialize()
        
        if not self.collection:
            return {"relevant_tables": [], "table_schemas": {}, "foreign_keys": []}
        
        # Enhance query with intent information
        enhanced_query = query
        if intent:
            entities = intent.get("entities", [])
            if entities:
                enhanced_query = f"{query}. Mentions: {', '.join(entities)}"
        
        # Search ChromaDB
        results = self.collection.query(
            query_texts=[enhanced_query],
            n_results=top_k * 2,  # Get extra results for filtering
            include=["documents", "metadatas", "distances"]
        )
        
        # Process results
        relevant_tables = []
        table_schemas = {}
        relevance_scores = {}
        
        if results and results["metadatas"]:
            for i, metadata in enumerate(results["metadatas"][0]):
                table_name = metadata["table_name"]
                distance = results["distances"][0][i] if results["distances"] else 1.0
                
                # Convert distance to similarity score (cosine distance)
                similarity = 1 - distance
                
                relevant_tables.append(table_name)
                relevance_scores[table_name] = float(similarity)
        
        # Get full schema for relevant tables from already-indexed data
        # NOTE: Schema was introspected at startup, no need to re-introspect
        # We retrieve from the stored schema cache instead
        if self.db_engine and hasattr(self, '_cached_schema'):
            full_schema = self._cached_schema
            for table_name in relevant_tables[:top_k]:
                if table_name in full_schema["tables"]:
                    table_schemas[table_name] = full_schema["tables"][table_name]
            
            # Filter foreign keys to only those involving relevant tables
            relevant_fks = [
                fk for fk in full_schema["foreign_keys"]
                if fk["table"] in relevant_tables[:top_k] 
                or fk["referenced_table"] in relevant_tables[:top_k]
            ]
        else:
            relevant_fks = []
        
        return {
            "relevant_tables": relevant_tables[:top_k],
            "table_schemas": table_schemas,
            "foreign_keys": relevant_fks,
            "relevance_scores": relevance_scores
        }
    
    def invoke(self, state: AgentState) -> AgentState:
        """
        Process the state to retrieve relevant schema information.
        
        Args:
            state: Current agent state
            
        Returns:
            Updated agent state with retrieved schema
        """
        state["current_agent"] = "schema_retrieval"
        
        try:
            # Initialize if needed
            if not self._initialized:
                self._initialize()
            
            # Connect to database if not already connected
            if not self.db_engine:
                db_connected = self.connect_to_database()
                if not db_connected:
                    add_to_processing_log(state, "WARNING: Could not connect to database")
            
            # Introspect and index schema if not already done
            # (In production, this would be done once at startup)
            # For now, we'll retrieve directly
            
            # Retrieve relevant schema
            result = self.retrieve_relevant_schema(
                query=state["question"],
                intent=state.get("intent"),
                top_k=5
            )
            
            # Update state
            state["relevant_tables"] = result["relevant_tables"]
            state["table_schemas"] = result["table_schemas"]
            state["foreign_keys"] = result["foreign_keys"]
            state["schema_relevance_scores"] = result["relevance_scores"]
            
            # Log the processing
            add_to_processing_log(
                state,
                f"Retrieved {len(result['relevant_tables'])} relevant tables: "
                f"{', '.join(result['relevant_tables'])}"
            )
            
        except Exception as e:
            error_msg = f"Schema retrieval failed: {str(e)}"
            state["error_message"] = error_msg
            add_to_processing_log(state, f"ERROR: {error_msg}")
            
            # Set empty defaults
            state["relevant_tables"] = []
            state["table_schemas"] = {}
            state["foreign_keys"] = []
        
        return state


# Singleton instance
_schema_agent_instance = None


def get_schema_agent() -> SchemaRetrievalAgent:
    """Get or create the Schema Retrieval Agent singleton."""
    global _schema_agent_instance
    if _schema_agent_instance is None:
        _schema_agent_instance = SchemaRetrievalAgent()
    return _schema_agent_instance


if __name__ == "__main__":
    # Test the agent
    print("Testing Schema Retrieval Agent\n" + "=" * 50)
    
    agent = get_schema_agent()
    
    # Test with SQLite (no setup required)
    test_db_url = "sqlite:///./data/sample.db"
    
    if agent.connect_to_database(test_db_url):
        print("✓ Connected to database")
        
        # Introspect schema
        schema = agent.introspect_schema()
        print(f"\nFound {len(schema.get('tables', {}))} tables")
        
        # Index schema
        agent.index_schema(schema)
        print("✓ Schema indexed")
        
        # Test retrieval
        test_query = "Show me all customers and their orders"
        result = agent.retrieve_relevant_schema(test_query, top_k=3)
        
        print(f"\nQuery: {test_query}")
        print(f"Relevant tables: {result['relevant_tables']}")
        print(f"Foreign keys: {len(result['foreign_keys'])}")
        
    else:
        print("✗ Could not connect to test database")
        print("Create a sample SQLite database first!")
