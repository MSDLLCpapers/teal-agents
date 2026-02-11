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

# Initialize app config
app_config = AppConfig(CONFIGS)


def get_db_engine():
    db_host = app_config.get(DB_HOST.env_name)
    db_port = app_config.get(DB_PORT.env_name)
    db_name = app_config.get(DB_NAME.env_name)
    db_user = app_config.get(DB_USER.env_name)
    db_password = app_config.get(DB_PASSWORD.env_name)
    
    SQLALCHEMY_DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    engine = create_engine(SQLALCHEMY_DATABASE_URL, echo=False, max_overflow=30)
    return engine


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session():
    return SessionLocal()


engine = get_db_engine()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
