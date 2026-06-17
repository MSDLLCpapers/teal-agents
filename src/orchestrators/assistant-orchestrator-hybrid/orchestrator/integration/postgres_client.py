"""
PostgreSQL client wrapper with pgvector support.

This module provides a wrapper around PostgreSQL database with pgvector
for storing and querying agent embeddings.
"""

import logging
from typing import Optional, Any, List, Tuple
from dataclasses import dataclass
from contextlib import contextmanager

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, Session
from langchain_openai import AzureOpenAIEmbeddings

from ska_utils import AppConfig
from configs import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
    DB_HOST,
    DB_PORT,
    DB_NAME,
    DB_USER,
    DB_PASSWORD,
)
from model.agent_registry import Base, AgentRegistry, ensure_pgvector_extension

logger = logging.getLogger(__name__)


@dataclass
class SearchDocument:
    """Document object matching LangChain's document structure."""
    page_content: str
    metadata: dict


class PostgresClient:
    """
    Wrapper for PostgreSQL database with pgvector extension.
    
    Provides centralized database management with support for:
    - Vector similarity search using pgvector
    - Agent registry management
    - Azure OpenAI embeddings integration
    """
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[str] = None,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        embedding_model: Optional[str] = None,
        skip_embeddings: bool = False
    ):
        """
        Initialize PostgreSQL client.
        
        Args:
            host: PostgreSQL host (defaults to config)
            port: PostgreSQL port (defaults to config)
            database: Database name (defaults to config)
            user: Database user (defaults to config)
            password: Database password (defaults to config)
            embedding_model: Azure OpenAI embedding model name (defaults to config)
            skip_embeddings: If True, skip embeddings initialization (for workers that only need DB access)
        """
        app_config = AppConfig()
        
        # Database connection parameters
        self.host = host or app_config.get(DB_HOST.env_name)
        self.port = port or app_config.get(DB_PORT.env_name)
        self.database = database or app_config.get(DB_NAME.env_name)
        self.user = user or app_config.get(DB_USER.env_name)
        self.password = password or app_config.get(DB_PASSWORD.env_name)
        
        # Embedding model configuration
        self.embedding_model = embedding_model or app_config.get(AZURE_OPENAI_EMBEDDING_DEPLOYMENT.env_name)
        
        # Azure OpenAI configuration
        self.openai_api_key = app_config.get(AZURE_OPENAI_API_KEY.env_name)
        self.openai_endpoint = app_config.get(AZURE_OPENAI_ENDPOINT.env_name)
        self.openai_api_version = app_config.get(AZURE_OPENAI_API_VERSION.env_name)
        
        # Initialize database connection
        self._initialize_database()
        
        # Initialize embeddings (optional for workers that only need DB access e.g. for content extraction)
        self._skip_embeddings = skip_embeddings
        if not skip_embeddings:
            self._initialize_embeddings()
            logger.info(f"Embedding model: {self.embedding_model}")
        else:
            self._embeddings = None
            logger.info("Embeddings initialization skipped (DB-only mode)")
        
        logger.info("PostgresClient initialized successfully")
        logger.info(f"Database: {self.host}:{self.port}/{self.database}")
    
    def _initialize_database(self) -> None:
        """Initialize database connection and create tables."""
        try:
            # Build connection URL
            connection_url = (
                f"postgresql+psycopg2://{self.user}:{self.password}"
                f"@{self.host}:{self.port}/{self.database}"
            )
            
            # Create engine with connection pooling
            self.engine = create_engine(
                connection_url,
                pool_size=5,
                pool_pre_ping=True,
                echo=False
            )
            
            # Ensure pgvector extension exists
            ensure_pgvector_extension(self.engine)
            
            # Create tables
            Base.metadata.create_all(self.engine)
            
            # Create session factory
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
            
            logger.info("Database initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def _initialize_embeddings(self) -> None:
        """Initialize Azure OpenAI embeddings."""
        try:
            if not self.openai_api_key or not self.openai_endpoint:
                raise ValueError("Azure OpenAI API key and endpoint are required")
            
            self._embeddings = AzureOpenAIEmbeddings(
                azure_deployment=self.embedding_model,
                openai_api_version=self.openai_api_version,
                azure_endpoint=self.openai_endpoint,
                api_key=self.openai_api_key
            )
            
            logger.info("Azure OpenAI embeddings initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize embeddings: {e}")
            raise
    
    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()
    
    @contextmanager
    def get_session_context(self):
        """
        Context manager for database sessions with automatic cleanup.
        
        Usage:
            with postgres_client.get_session_context() as session:
                # use session
                session.commit()
        
        Yields:
            SQLAlchemy Session instance
        """
        session = self.get_session()
        try:
            yield session
        finally:
            session.close()
    
    def get_all_documents(self) -> dict[str, Any]:
        """
        Get all active documents from the agent registry.
        
        Returns:
            Dictionary with 'ids', 'documents', 'metadatas' keys matching VectorDB format
        """
        with self.get_session() as session:
            agents = session.query(AgentRegistry).filter_by(is_active=True).all()
            
            ids = []
            documents = []
            metadatas = []
            
            for agent in agents:
                ids.append(agent.agent_name)
                documents.append(agent.description)
                metadatas.append(agent.to_metadata_dict())
            
            return {
                'ids': ids,
                'documents': documents,
                'metadatas': metadatas
            }
    
    def similarity_search_with_score(
        self,
        query: str,
        k: int = 10
    ) -> List[Tuple[SearchDocument, float]]:
        """
        Perform similarity search with scores using pgvector.
        
        Args:
            query: Search query text
            k: Number of results to return
            
        Returns:
            List of (document, score) tuples where score is normalized similarity (0-1)
        """
        if self._skip_embeddings or self._embeddings is None:
            raise RuntimeError(
                "Embeddings not initialized. Cannot perform similarity search. "
                "Initialize PostgresClient with skip_embeddings=False."
            )
        
        try:
            # Generate embedding for query
            query_embedding = self._embeddings.embed_query(query)
            
            with self.get_session() as session:
                # Use pgvector's <=> operator for cosine distance
                # Note: <=> returns distance (lower is better), we convert to similarity
                results = session.query(
                    AgentRegistry,
                    AgentRegistry.description_embeddings.cosine_distance(query_embedding).label('distance')
                ).filter(
                    AgentRegistry.is_active == True,
                    AgentRegistry.description_embeddings.isnot(None)
                ).order_by(
                    'distance'
                ).limit(k).all()
                
                # Convert to (document, score) tuples
                search_results = []
                for agent, distance in results:
                    # Convert distance to similarity score (0-1 range)
                    # Cosine distance is in [0, 2], convert to similarity
                    similarity_score = 1 - (distance / 2) if distance < 2 else 0
                    
                    doc = SearchDocument(
                        page_content=agent.description,
                        metadata=agent.to_metadata_dict()
                    )
                    
                    search_results.append((doc, float(similarity_score)))
                
                logger.debug(f"Similarity search returned {len(search_results)} results")
                return search_results
                
        except Exception as e:
            logger.error(f"Similarity search failed: {e}")
            raise
    
    def get_collection_count(self) -> int:
        """
        Get the number of active agents in the registry.
        
        Returns:
            Number of active agents
        """
        with self.get_session() as session:
            count = session.query(func.count(AgentRegistry.id)).filter_by(is_active=True).scalar()
            return count or 0
    
    def close(self):
        """Close database connections."""
        if hasattr(self, 'engine'):
            self.engine.dispose()
            logger.info("Database connections closed")
