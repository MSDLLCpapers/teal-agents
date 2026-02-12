from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from ska_utils import AppConfig
from configs import (
    DB_HOST,
    DB_PORT,
    DB_NAME,
    DB_USER,
    DB_PASSWORD,
    CONFIGS,
)

# Add configs and initialize app config
AppConfig.add_configs(CONFIGS)
app_config = AppConfig()

# Lazy initialization for engine and session
_engine = None
_SessionLocal = None


def get_db_engine():
    global _engine
    if _engine is None:
        db_host = app_config.get(DB_HOST.env_name)
        db_port = app_config.get(DB_PORT.env_name)
        db_name = app_config.get(DB_NAME.env_name)
        db_user = app_config.get(DB_USER.env_name)
        db_password = app_config.get(DB_PASSWORD.env_name)
        
        SQLALCHEMY_DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        _engine = create_engine(SQLALCHEMY_DATABASE_URL, echo=False, max_overflow=30)
    return _engine


def _get_session_local():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_db_engine())
    return _SessionLocal


def get_db():
    SessionLocal = _get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session():
    SessionLocal = _get_session_local()
    return SessionLocal()


Base = declarative_base()
