"""
SQLAlchemy models for PostgreSQL database.

This module defines the ORM models for storing agent registry data
with vector embeddings using pgvector extension.
"""

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ARRAY,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from pgvector.sqlalchemy import Vector

Base = declarative_base()


class AgentRegistry(Base):
    """
    Agent Registry model storing agent metadata and embeddings.
    
    Attributes:
        id: Auto-incrementing primary key
        agent_name: Unique agent identifier
        description: Full text description of agent capabilities
        version: Agent version string
        created_at: Timestamp of agent creation
        updated_at: Timestamp of last update
        extra_info: Additional metadata as JSONB
        is_active: Whether agent is currently active
        tags: Array of tag strings
        description_keywords: Array of keyword strings extracted from description
        description_embeddings: Vector embeddings of description (1536 dimensions)
        deployment_name: Unique deployment identifier
        learned_keywords: Array of learned keyword strings from usage
    """
    
    __tablename__ = "agent_registry"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)
    version = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    extra_info = Column(JSONB, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    tags = Column(ARRAY(Text), nullable=True)
    description_keywords = Column(ARRAY(Text), nullable=True)
    description_embeddings = Column(Vector(1536), nullable=True)
    deployment_name = Column(String(255), unique=True, nullable=False, index=True)
    learned_keywords = Column(ARRAY(Text), nullable=True)
    
    def __repr__(self):
        return f"<AgentRegistry(agent_name='{self.agent_name}', is_active={self.is_active})>"
    
    def to_metadata_dict(self):
        """Convert to metadata dictionary matching VectorDB format."""
        return {
            'agent_name': self.agent_name,
            'name': self.agent_name,
            'description': self.description,
            'deployment_name': self.deployment_name,
            'version': self.version,
            'is_active': self.is_active,
            'tags': self.tags,
            'keywords': self.description_keywords,
            'learned_keywords': self.learned_keywords,
            'extra_info': self.extra_info,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


def ensure_pgvector_extension(engine):
    """
    Ensure the pgvector extension is enabled in the database.
    
    Args:
        engine: SQLAlchemy engine instance
    """
    from sqlalchemy import text
    
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
