"""
ChromaDB client wrapper.

This module provides a wrapper around ChromaDB client initialization
and common operations.
"""

import logging
from typing import Optional, Any

import chromadb
from chromadb.config import Settings

from ska_utils import AppConfig
from configs import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
    CHROMA_PERSIST_DIR,
    CHROMA_COLLECTION_NAME,
)

logger = logging.getLogger(__name__)


class ChromaClient:
    """
    Wrapper for ChromaDB client with LangChain integration.
    
    Provides centralized ChromaDB client management with support for:
    - Persistent storage
    - LangChain embeddings integration
    - Collection management
    """
    
    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: Optional[str] = None,
        embedding_model: Optional[str] = None
    ):
        """
        Initialize ChromaDB client.
        
        Args:
            persist_directory: Directory to persist ChromaDB data (defaults to config)
            collection_name: Name of the default collection (defaults to config)
            embedding_model: Azure OpenAI embedding model name (defaults to config)
        """
        app_config = AppConfig()
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.embedding_model = embedding_model or app_config.get(AZURE_OPENAI_EMBEDDING_DEPLOYMENT.env_name)
        
        # Azure OpenAI configuration
        self.openai_api_key = app_config.get(AZURE_OPENAI_API_KEY.env_name)
        self.openai_endpoint = app_config.get(AZURE_OPENAI_ENDPOINT.env_name)
        self.openai_api_version = app_config.get(AZURE_OPENAI_API_VERSION.env_name)
        
        self._client: Optional[chromadb.PersistentClient] = None
        self._embeddings = None
        self._vectorstore = None
        
    def _ensure_initialized(self) -> None:
        """Ensure client is initialized."""
        if self._client is None:
            self._initialize()
    
    def _initialize(self) -> None:
        """Initialize ChromaDB client and LangChain components."""
        try:
            from langchain_openai import AzureOpenAIEmbeddings
            from langchain_community.vectorstores import Chroma
            
            if not self.openai_api_key or not self.openai_endpoint:
                raise ValueError("Azure OpenAI API key and endpoint are required")
            
            # Initialize Azure OpenAI embeddings via LangChain
            self._embeddings = AzureOpenAIEmbeddings(
                azure_deployment=self.embedding_model,
                openai_api_version=self.openai_api_version,
                azure_endpoint=self.openai_endpoint,
                api_key=self.openai_api_key
            )
            
            # Initialize ChromaDB client
            self._client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # Initialize LangChain Chroma vectorstore
            self._vectorstore = Chroma(
                client=self._client,
                collection_name=self.collection_name,
                embedding_function=self._embeddings
            )
            
            logger.info(f"ChromaDB client initialized successfully")
            logger.info(f"Persist directory: {self.persist_directory}")
            logger.info(f"Collection: {self.collection_name}")
            logger.info(f"Embedding model: {self.embedding_model}")
            
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB client: {e}")
            raise
    
    @property
    def client(self) -> chromadb.PersistentClient:
        """Get the ChromaDB client instance."""
        self._ensure_initialized()
        return self._client
    
    @property
    def embeddings(self):
        """Get the LangChain embeddings instance."""
        self._ensure_initialized()
        return self._embeddings
    
    @property
    def vectorstore(self):
        """Get the LangChain Chroma vectorstore instance."""
        self._ensure_initialized()
        return self._vectorstore
    
    def get_collection(self, name: Optional[str] = None):
        """
        Get a ChromaDB collection.
        
        Args:
            name: Collection name (defaults to configured collection)
            
        Returns:
            ChromaDB collection
        """
        self._ensure_initialized()
        return self._client.get_collection(name=name or self.collection_name)
    
    def get_all_documents(self, collection_name: Optional[str] = None) -> dict[str, Any]:
        """
        Get all documents from a collection.
        
        Args:
            collection_name: Collection name (defaults to configured collection)
            
        Returns:
            Dictionary with 'ids', 'documents', 'metadatas'
        """
        collection = self.get_collection(collection_name)
        return collection.get(include=["documents", "metadatas"])
    
    def similarity_search_with_score(
        self,
        query: str,
        k: int = 10
    ) -> list[tuple]:
        """
        Perform similarity search with scores.
        
        Args:
            query: Search query
            k: Number of results to return
            
        Returns:
            List of (document, score) tuples
        """
        self._ensure_initialized()
        return self._vectorstore.similarity_search_with_score(query=query, k=k)
    
    def get_collection_count(self, collection_name: Optional[str] = None) -> int:
        """
        Get the number of documents in a collection.
        
        Args:
            collection_name: Collection name (defaults to configured collection)
            
        Returns:
            Number of documents
        """
        collection = self.get_collection(collection_name)
        return collection.count()
