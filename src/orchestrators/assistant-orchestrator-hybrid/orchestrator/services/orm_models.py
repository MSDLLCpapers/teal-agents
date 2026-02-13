from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Column, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP

from .database import Base


class AgentRegistry(Base):
    __tablename__ = "agent_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)
    version = Column(String(50), nullable=True)
    created_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
        index=True,
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
        index=True,
    )
    extra_info = Column(JSONB, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    tags = Column(ARRAY(Text), nullable=True)
    description_keywords = Column(ARRAY(Text), nullable=True)
    description_embeddings = Column(Vector(1536), nullable=True)
    deployment_name = Column(String(255), unique=False, nullable=False, index=True)
    
