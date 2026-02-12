"""
PostgreSQL client for Celery workers.

This module provides database session management for the content_update
Celery worker process. It creates its own database connection separate
from the main FastAPI application's PostgresClient.
"""

import logging
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from ska_utils import AppConfig
from configs import (
    DB_HOST,
    DB_PORT,
    DB_NAME,
    DB_USER,
    DB_PASSWORD,
)

logger = logging.getLogger(__name__)

# Global session factory (lazy-initialized)
_SessionLocal = None


def _get_session_factory():
    """Get or create the SQLAlchemy session factory."""
    global _SessionLocal
    
    if _SessionLocal is None:
        app_config = AppConfig()
        
        # Build PostgreSQL connection URL
        host = app_config.get(DB_HOST.env_name)
        port = app_config.get(DB_PORT.env_name)
        database = app_config.get(DB_NAME.env_name)
        user = app_config.get(DB_USER.env_name)
        password = app_config.get(DB_PASSWORD.env_name)
        
        connection_url = (
            f"postgresql+psycopg2://{user}:{password}"
            f"@{host}:{port}/{database}"
        )
        
        # Create engine with connection pooling
        engine = create_engine(
            connection_url,
            pool_size=5,
            pool_pre_ping=True,
            echo=False
        )
        
        # Create session factory
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine
        )
        
        logger.info(f"PostgreSQL session factory initialized for Celery worker: {host}:{port}/{database}")
    
    return _SessionLocal


def get_session() -> Session:
    """
    Get a new database session.
    
    Returns:
        SQLAlchemy Session instance
        
    Note:
        Caller is responsible for closing the session.
        Prefer using get_session_context() for automatic cleanup.
    """
    SessionLocal = _get_session_factory()
    return SessionLocal()


@contextmanager
def get_session_context():
    """
    Context manager for database sessions with automatic cleanup.
    
    Usage:
        with get_session_context() as session:
            # use session
            session.commit()
    """
    session = get_session()
    try:
        yield session
    finally:
        session.close()
